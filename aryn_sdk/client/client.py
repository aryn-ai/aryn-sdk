from contextlib import nullcontext
import json
import logging
import mimetypes
from os import PathLike
from typing import Any, BinaryIO, ContextManager, Optional, Tuple, Type, TypeVar, Union

import httpx
from httpx import Request
from pydantic import JsonValue

from .config import ArynConfig
from .exceptions import ArynSDKException
from .response import Response, PaginatedResponse, SimpleResponse
from .tasks import AsyncTask
from ..types.docset import DocSetMetadata, DocSetUpdate
from ..types.document import Document, DocumentMetadata, FieldUpdates
from ..types.prompt import PromptType
from ..types.schema import Schema
from ..types.search import SearchRequest, SearchResponse
from ..types.task import AsyncTaskMap
from ..types.transforms import TransformResponse

ResponseType = TypeVar("ResponseType")


class Client:

    def __init__(
        self,
        aryn_url: str = "https://api.aryn.ai",
        aryn_api_key: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.aryn_url = aryn_url

        self.config = ArynConfig(aryn_api_key=aryn_api_key, aryn_url=aryn_url)

        headers = (extra_headers or {}) | {"Authorization": f"Bearer {self.config.api_key()}"}
        self.client = httpx.Client(base_url=self.config.aryn_url(), headers=headers, timeout=90.0)

    def _make_raw_request(self, req: Request) -> httpx.Response:
        res = self.client.send(req)
        if res.status_code >= 300:
            raise ArynSDKException(res)

        return res

    def _make_request(
        self,
        req: Request,
        response_type: Type[ResponseType],
    ) -> Response[ResponseType]:
        res = self._make_raw_request(req)

        return Response(raw_response=res, value=response_type(**res.json()))

    def _make_paginated_request(
        self, req: Request, responseType: Type[ResponseType], list_key: str, *request_args, **request_kwargs
    ) -> PaginatedResponse[ResponseType]:
        res = self._make_raw_request(req)
        return PaginatedResponse(
            client=self,
            first_response=res,
            response_type=responseType,
            list_key=list_key,
            request_args=list(request_args),
            request_kwargs=request_kwargs,
        )

    # ----------------------------------------------
    # DocSet APIs
    # ----------------------------------------------

    def create_docset(
        self,
        *,
        name: str,
        properties: Optional[dict[str, JsonValue]] = None,
        schema: Optional[Schema] = None,
        prompts: Optional[dict[PromptType, str]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> Response[DocSetMetadata]:
        json_body = {"name": name, "properties": properties, "prompts": prompts}
        if schema is not None:
            json_body["schema"] = schema.model_dump()

        req = self.client.build_request("POST", "/v1/storage/docsets", json=json_body, headers=extra_headers)
        return self._make_request(req, DocSetMetadata)

    def clone_docset(
        self, *, docset_id: str, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[DocSetMetadata]:
        return self._make_request(
            self.client.build_request("POST", f"/v1/storage/docsets/{docset_id}/clone", headers=extra_headers),
            DocSetMetadata,
        )

    def list_docsets(
        self,
        *,
        name_eq: Optional[str] = None,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> PaginatedResponse[DocSetMetadata]:

        params: dict[str, Any] = {}
        if name_eq is not None:
            params["name_eq"] = name_eq
        if page_size is not None:
            params["page_size"] = page_size
        if page_token is not None:
            params["page_token"] = page_token

        args = ("GET", "/v1/storage/docsets")
        kwargs: dict[str, Any] = {"params": params or None, "headers": extra_headers}
        req = self.client.build_request(*args, **kwargs)
        return self._make_paginated_request(req, DocSetMetadata, "items", *args, **kwargs)

    def get_docset(self, *, docset_id: str, extra_headers: Optional[dict[str, str]] = None) -> Response[DocSetMetadata]:
        return self._make_request(
            self.client.build_request("GET", f"/v1/storage/docsets/{docset_id}", headers=extra_headers), DocSetMetadata
        )

    def update_docset(
        self, *, docset_id: str, update: DocSetUpdate, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[DocSetMetadata]:
        return self._make_request(
            self.client.build_request(
                "PATCH", f"/v1/storage/docsets/{docset_id}", json=update.model_dump(), headers=extra_headers
            ),
            DocSetMetadata,
        )

    def set_readonly_docset(
        self, *, docset_id: str, readonly: bool, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[DocSetMetadata]:
        return self._make_request(
            self.client.build_request(
                "POST", f"/v1/storage/docsets/{docset_id}/readonly/{int(readonly)}", headers=extra_headers
            ),
            DocSetMetadata,
        )

    def delete_docset(
        self, *, docset_id: str, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[DocSetMetadata]:
        return self._make_request(
            self.client.build_request("DELETE", f"/v1/storage/docsets/{docset_id}", headers=extra_headers),
            DocSetMetadata,
        )

    # ----------------------------------------------
    # Document APIs
    # ----------------------------------------------

    # TODO: Better typing of DocParse options.
    def add_doc(
        self,
        *,
        file: Union[BinaryIO, str, PathLike],
        docset_id: str,
        options: Optional[dict[str, Any]] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> Response[DocumentMetadata]:
        file_request: Any

        if isinstance(file, (str, PathLike)):
            if str(file).startswith("s3://"):
                try:
                    import boto3
                except ImportError:
                    raise ImportError("Please install the boto3 library to read from S3 URLs.")

                s3 = boto3.client("s3")
                bucket, key = str(file)[5:].split("/", 1)
                response = s3.get_object(Bucket=bucket, Key=key)
                stream = response["Body"]
            else:
                stream = open(file, "rb")

            mime_type, _ = mimetypes.guess_type(file)
            file_request = (file, stream, mime_type or "application/octet-stream")
        else:
            file_request = file

        files: dict[str, Any] = {"file": file_request}

        if options is not None:
            files["options"] = json.dumps(options).encode("utf-8")

        req = self.client.build_request(
            "POST", f"/v1/storage/docsets/{docset_id}/docs", files=files, headers=extra_headers
        )
        return self._make_request(req, DocumentMetadata)

    # TODO: Decide what filtering we want to support here
    def list_docs(
        self,
        *,
        docset_id: str,
        page_size: Optional[int] = None,
        page_token: Optional[str] = None,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> PaginatedResponse[DocumentMetadata]:

        page_param: dict[str, Any] = {}
        if page_size is not None:
            page_param["page_size"] = page_size
        if page_token is not None:
            page_param["page_token"] = page_token

        args = ("GET", f"/v1/storage/docsets/{docset_id}/docs")
        kwargs: dict[str, Any] = {"params": page_param or None, "headers": extra_headers}
        req = self.client.build_request(*args, **kwargs)
        return self._make_paginated_request(req, DocumentMetadata, "items", *args, **kwargs)

    def get_doc(
        self,
        *,
        docset_id,
        doc_id,
        include_elements: bool = True,
        include_binary: bool = False,
        extra_headers: Optional[dict[str, str]] = None,
    ) -> Response[Document]:
        data = {"include_elements": include_elements, "include_binary": include_binary}
        req = self.client.build_request(
            "GET", f"/v1/storage/docsets/{docset_id}/docs/{doc_id}", data=data, headers=extra_headers
        )
        return self._make_request(req, Document)

    def get_doc_binary(
        self,
        *,
        docset_id: str,
        doc_id: str,
        file: Union[BinaryIO, PathLike, str],
        extra_headers: Optional[dict[str, str]] = None,
    ) -> None:
        # TODO: This should really be a streaming response, and I'm not sure
        # that writing it to a file is the best way to handle it, but it simplifies
        # the typing of the response for now.
        req = self.client.build_request(
            "GET", f"/v1/storage/docsets/{docset_id}/docs/{doc_id}/binary", headers=extra_headers
        )
        res = self._make_raw_request(req)

        if isinstance(file, (str, PathLike)):
            cm: ContextManager[BinaryIO] = open(file, "wb")
        else:
            cm = nullcontext(file)

        with cm as file_obj:
            for data in res.iter_bytes():
                file_obj.write(data)

    def update_doc_properties(
        self, *, docset_id: str, doc_id: str, updates: FieldUpdates, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[Document]:
        req = self.client.build_request(
            "PATCH",
            f"/v1/storage/docsets/{docset_id}/docs/{doc_id}/properties",
            json=updates.model_dump(),
            headers=extra_headers,
        )
        return self._make_request(req, Document)

    def delete_doc(
        self, *, docset_id: str, doc_id: str, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[DocumentMetadata]:
        return self._make_request(
            self.client.build_request(
                "DELETE", f"/v1/storage/docsets/{docset_id}/docs/{doc_id}", headers=extra_headers
            ),
            DocumentMetadata,
        )

    # ----------------------------------------------
    # Search APIs
    # ----------------------------------------------
    def search(
        self, *, docset_id, query: SearchRequest, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[SearchResponse]:
        req = self.client.build_request(
            "POST", f"/v1/query/search/{docset_id}", json=query.model_dump(), headers=extra_headers
        )
        return self._make_request(req, SearchResponse)

    # ----------------------------------------------
    # Transform APIs
    # ----------------------------------------------

    def extract_properties(
        self, *, docset_id: str, schema: Schema, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[TransformResponse]:
        req = self.client.build_request(
            "POST",
            "/v1/jobs/extract-properties",
            params={"docset_id": docset_id},
            json=schema.model_dump(),
            headers=extra_headers,
        )
        return self._make_request(req, TransformResponse)

    def extract_properties_async(
        self, *, docset_id: str, schema: Schema, extra_headers: Optional[dict[str, str]] = None
    ) -> AsyncTask[TransformResponse]:
        req = self.client.build_request(
            "POST",
            "/v1/async/submit/jobs/extract-properties",
            params={"docset_id": docset_id},
            json=schema.model_dump(),
            headers=extra_headers,
        )

        res = self._make_raw_request(req)
        task_id = res.json()["task_id"]
        return AsyncTask(
            client=self,
            task_id=task_id,
            method="POST",
            path="/jobs/extract-properties",
            response_type=TransformResponse,
        )

    def delete_properties(
        self, *, docset_id: str, schema: Schema, extra_headers: Optional[dict[str, str]] = None
    ) -> Response[TransformResponse]:
        req = self.client.build_request(
            "POST",
            "/v1/jobs/delete-properties",
            params={"docset_id": docset_id},
            json=schema.model_dump(),
            headers=extra_headers,
        )
        return self._make_request(req, TransformResponse)

    def delete_properties_async(
        self, *, docset_id: str, schema: Schema, extra_headers: Optional[dict[str, str]] = None
    ) -> AsyncTask[TransformResponse]:
        req = self.client.build_request(
            "POST",
            "/v1/async/submit/jobs/delete-properties",
            params={"docset_id": docset_id},
            json=schema.model_dump(),
            headers=extra_headers,
        )

        res = self._make_raw_request(req)
        task_id = res.json()["task_id"]
        return AsyncTask(
            client=self,
            task_id=task_id,
            method="POST",
            path="/jobs/delete-properties",
            response_type=TransformResponse,
        )

    # ----------------------------------------------
    # Async task APIs
    # ----------------------------------------------

    def _get_task_and_filters(self, task: Union[AsyncTask, str]) -> Tuple[str, Optional[str], Optional[str]]:
        method_filter = None
        path_filter = None

        if isinstance(task, AsyncTask):
            task_id = task.task_id

            if (method := task.method) is not None:
                method_filter = method

            if (path := task.path) is not None:
                path_filter = path
        else:
            task_id = task

        return task_id, method_filter, path_filter

    def list_async_tasks(self) -> Response[AsyncTaskMap]:
        req = self.client.build_request("GET", "/v1/async/list")
        return self._make_request(req, AsyncTaskMap)

    def cancel_async_task(self, task: Union[AsyncTask, str]) -> SimpleResponse:
        task_id, method_filter, path_filter = self._get_task_and_filters(task)

        req = self.client.build_request(
            "POST", f"/v1/async/cancel/{task_id}", params={"method_filter": method_filter, "path_filter": path_filter}
        )

        res = self._make_raw_request(req)
        return SimpleResponse(res)

    def _get_async_result_internal(self, task: Union[AsyncTask, str]) -> httpx.Response:
        task_id, method_filter, path_filter = self._get_task_and_filters(task)

        req = self.client.build_request(
            "GET", f"/v1/async/result/{task_id}", params={"method_filter": method_filter, "path_filter": path_filter}
        )

        return self._make_raw_request(req)

    def get_async_result(self, task: Union[AsyncTask, str]) -> Union[SimpleResponse, Response]:
        res = self._get_async_result_internal(task)

        if res.status_code == 200:
            if res.headers.get("Content-Type").lower() == "application/json":
                content = res.json()
            else:
                content = res.content

            return Response(res, content)

        elif res.status_code == 202:
            return SimpleResponse(res)

        # This should be unreachable, as other status codes should be handled by _make_raw_request
        logging.error(f"Unexpected status code {res.status_code} for async task {task}")
        raise ArynSDKException(res)

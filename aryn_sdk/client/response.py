from typing import Any, Generic, Iterator, Optional, Type, TypeVar, TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .client import Client

T = TypeVar("T")


class SimpleResponse:
    """A simple http response intended for cases where the response body is not needed."""

    raw_request: httpx.Request
    raw_response: httpx.Response

    def __init__(self, raw_response: httpx.Response) -> None:
        self.raw_request = raw_response.request
        self.raw_response = raw_response

    @property
    def call_id(self) -> str:
        return self.raw_response.headers.get("x-aryn-call-id")

    @property
    def status_code(self) -> int:
        return self.raw_response.status_code


class Response(SimpleResponse, Generic[T]):
    raw_request: httpx.Request
    raw_response: httpx.Response
    value: T

    def __init__(self, raw_response: httpx.Response, value: T) -> None:
        super().__init__(raw_response)
        self.value = value


class PaginatedResponse(Generic[T]):
    curr_raw_response: httpx.Response
    curr_page: list[T]
    _next_token: Optional[str]

    def __init__(
        self,
        client: "Client",
        first_response: httpx.Response,
        response_type: Type[T],
        list_key: str,
        request_args: list[Any],
        request_kwargs: dict[str, Any],
    ) -> None:
        self._response_type = response_type
        self._client = client
        self._list_key = list_key
        self._request_args = request_args
        self._request_kwargs = request_kwargs

        self._process_response(first_response)

    def _process_response(self, response: httpx.Response) -> None:
        self.curr_raw_response = response
        json_res = response.json()
        self._next_token = json_res.get("next_page_token")
        list_of_dicts = json_res.get(self._list_key, [])

        # TODO: Would like to get this to work with TypeAdapter[list[T]], but
        # that doesn't seem to work.
        self.curr_page = [self._response_type(**v) for v in list_of_dicts]

    def _get_next_page(self) -> None:
        if self._next_token is None:
            self.curr_page = []
            return

        curr_json = self._request_kwargs.get("params", {}) or {}
        curr_json.update({"page_token": self._next_token})
        self._request_kwargs["params"] = curr_json

        new_request = self._client.client.build_request(*self._request_args, **self._request_kwargs)

        self.curr_raw_response = self._client._make_raw_request(new_request)
        self._process_response(self.curr_raw_response)

    @property
    def call_id(self) -> str:
        return self.curr_raw_response.headers.get("x-aryn-call-id")

    @property
    def status_code(self) -> int:
        return self.curr_raw_response.status_code

    def get_all(self) -> list[T]:
        return list(self)

    def iter_page(self) -> Iterator[Response[list[T]]]:
        yield Response[list[T]](self.curr_raw_response, self.curr_page)
        while self._next_token is not None:
            self._get_next_page()
            yield Response[list[T]](self.curr_raw_response, self.curr_page)

    def __iter__(self) -> Iterator[T]:
        yield from self.curr_page
        while self._next_token is not None:
            self._get_next_page()
            yield from self.curr_page

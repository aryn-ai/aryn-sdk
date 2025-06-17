from os import PathLike
from typing import BinaryIO, Literal, Optional, Union, Any
from urllib.parse import urlparse, urlunparse
from collections.abc import Mapping
from .config import ArynConfig
import httpx
import sys
import json
import logging
import pandas as pd
import numpy as np
from collections import OrderedDict
from PIL import Image
import base64
import io
import xml.etree.ElementTree as ET

# URL for Aryn DocParse
ARYN_DOCPARSE_URL = "https://api.aryn.cloud/v1/document/partition"

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)
_logger.addHandler(logging.StreamHandler(sys.stderr))

g_version = "0.2.8"
g_parameters = {"path_filter": "^/v1/document/partition$"}


class PartitionError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class PartitionTaskError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class PartitionTaskNotFoundError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class BoolFlag:
    """
    A boxed boolean that can be mutated and passed around by reference.
    """

    __slots__ = "val"

    def __init__(self, val: bool) -> None:
        self.val = val

    def set(self, val: bool) -> None:
        self.val = val

    def get(self) -> bool:
        return self.val


def partition_file(
    file: Union[BinaryIO, str, PathLike],
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    threshold: Optional[Union[float, Literal["auto"]]] = None,
    text_mode: Optional[str] = None,
    table_mode: Optional[str] = None,
    use_ocr: Optional[bool] = None,
    summarize_images: bool = False,
    ocr_language: Optional[str] = None,
    extract_table_structure: Optional[bool] = None,
    text_extraction_options: Optional[dict[str, Any]] = None,
    table_extraction_options: Optional[dict[str, Any]] = None,
    extract_images: bool = False,
    extract_image_format: Optional[str] = None,
    selected_pages: Optional[list[Union[list[int], int]]] = None,
    chunking_options: Optional[dict[str, Any]] = None,
    aps_url: Optional[str] = None,  # deprecated in favor of docparse_url
    docparse_url: Optional[str] = None,
    ssl_verify: bool = True,
    output_format: Optional[str] = None,
    markdown_options: Optional[dict[str, Any]] = None,
    output_label_options: Optional[dict[str, Any]] = None,
    return_pdf_base64: bool = False,
    trace_id: Optional[str] = None,  # deprecated
    extra_headers: Optional[dict[str, str]] = None,
    cancel_flag: Optional[BoolFlag] = None,
    add_to_docset_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> dict:
    """
    Sends file to Aryn DocParse and returns a dict of its document structure and text

    Args:
        file: (pdf, docx, doc, jpg, or png, etc.) file to partition
            (see all supported file types at https://docs.aryn.ai/docparse/formats_supported)
        aryn_api_key: Aryn api key, provided as a string
            You can get a key here: https://www.aryn.ai/get-started
        aryn_config: ArynConfig object, used for finding an api key.
            If aryn_api_key is set it will override this.
            default: The default ArynConfig looks in the env var ARYN_API_KEY and the file ~/.aryn/config.yaml
        threshold: specify the cutoff for detecting bounding boxes. Must be set to "auto" or
            a floating point value between 0.0 and 1.0.
            default: None (Aryn DocParse will choose)
        text_mode:  Allows for specifying the text extraction mode. Valid options are 'inline_fallback_to_ocr',
            'inline', 'ocr_standard', and 'ocr_vision'. 'inline_fallback_to_ocr' will use the standard text
            extraction to extract text embedded in the document where possible and will use the standard OCR pipeline
            when text is detected but not embedded in the document. 'inline' will use only the standard text extraction
            pipeline to extract text embedded in the document and not use OCR, 'fine_grained' will use a more
            fine-grained text extraction pipeline, 'ocr_standard' will use only the standard OCR pipeline, and
            'ocr_vision' will use a vision OCR pipeline. If a text_mode option is specified, it will override use_ocr
            and text_extraction_options even if they are also specified.
            Deprecated options: 'standard', 'standard_ocr', 'vision_ocr', and 'fine_grained'.
            default: 'inline_fallback_to_ocr'
        table_mode: Specify the table structure extraction mode.  Valid options are 'none', 'standard', 'vision', and 'custom'
            'none' will not extract table structure (equivalent to extract_table_structure=False),
            'standard' will use the standard hybrid table structure extraction pipeline described at https://docs.aryn.ai/docparse/processing_options,
            'vision' will use a vision model to extract table structure,
            'custom' will use the custom expression described by the model_selection parameter in the table_extraction_options.
        use_ocr: deprecated, use text_mode instead.
            extract text using an OCR model instead of extracting embedded text in PDF.
            default: False
        summarize_images: Generate a text summary of detected images using a VLM.
        ocr_language: specify the language to use for OCR. If not set, the language will be english.
            default: English
        extract_table_structure: deprecated, use table_mode instead.
            extract tables and their structural content.
            default: False
        text_extraction_options: 'ocr_text_mode' is deprecated, use text_mode instead.
            Specify options for text extraction, supports 'ocr_text_mode', with valid options 'vision' and 'standard' and boolean
            'remove_line_breaks'. For 'ocr_text_mode', attempt to extract all non-table text
            using vision models if 'vision', else will use the standard OCR pipeline. Vision is useful for documents with complex layouts
            or non-standard fonts. 'remove_line_breaks' will remove line breaks from the text.
            default: {'remove_line_breaks': True}
        table_extraction_options: Specify options for table extraction. Only enabled if table extraction
            is enabled. Default is {}. Options:
            - 'include_additional_text': Attempt to enhance the table structure by merging in tokens from
                text extraction. This can be useful for tables with missing or misaligned text. Default: False
            - 'model_selection': expression to instruct DocParse how to choose which model to use for table
                extraction. See https://docs.aryn.ai/docparse/processing_options for more details. Default:
                "pixels > 500 -> deformable_detr; table_transformer"
        extract_images: extract image contents. By default returns the image in base64 encoded ppm format,
              but can be configured to return the image in other formats via the extract_image_format parameter.
            default: False
        extract_image_format: specify the format of the extracted images. Only applies when extract_images=True.
              Must be one of ["PPM", "PNG", "JPEG"]
            default: PPM
        selected_pages: list of individual pages (1-indexed) from the pdf to partition
            default: None
        chunking_options: Specify options for chunking the document.
            You can use the default the chunking options by setting this to {}.
            Here is an example set of chunking options:
            {
                'strategy': 'context_rich',
                'tokenizer': 'openai_tokenizer',
                'tokenizer_options': {'model_name': 'text-embedding-3-small'},
                'max_tokens': 512,
                'merge_across_pages': True
            }
            default: None
        aps_url: url of Aryn DocParse endpoint.
            Left in for backwards compatibility. Use docparse_url instead.
        docparse_url: url of Aryn DocParse endpoint.
        ssl_verify: verify ssl certificates. In databricks, set this to False to fix ssl imcompatibilities.
        output_format: controls output representation; can be set to "markdown" or "json"
            default: None (JSON elements)
        markdown_options: A dictionary for configuring markdown output behavior. It supports three options:
            include_headers, a boolean specifying whether to include headers in the markdown output, include_footers,
            a boolean specifying whether to include footers in the markdown output, and include_pagenum, a boolean
            specifying whether to include page numbers in the markdown output. Here is an example set of markdown
            options:
                {
                    "include_headers": True,
                    "include_footers": True,
                    "include_pagenum": True
                }
        output_label_options: A dictionary for configuring output label behavior. It supports three options:
            promote_title, a boolean specifying whether to pick the largest element by font size on the first page
                from among the elements on that page that have one of the types specified in title_candidate_elements
                and promote it to type "Title" if there is no element on the first page of type "Title" already.
            title_candidate_elements, a list of strings representing the label types allowed to be promoted to
                a title.
            orientation_correction, a boolean specifying whether to pagewise rotate pages to the correct orientation
                based off the orientation of text. Pages are rotated by increments of 90 degrees to correct their
                orientation.
            Here is an example set of output label options:
                {
                    "promote_title": True,
                    "title_candidate_elements": ["Section-header", "Caption"],
                    "orientation_correction": True
                }
            default: None (no element is promoted to "Title")
        trace_id: deprecated
        return_pdf_base64: return the pdf used for partitioning as a base64 encoded string
        extra_headers: dict of HTTP headers to send to DocParse
        cancel_flag: way to interrupt partitioning from the outside
        add_to_docset_id: An optional docset_id to which to add the document.

    Returns:
        A dictionary containing "status", "elements", and possibly "error"
        If output_format is "markdown" then it returns a dictionary of "status", "markdown", and possibly "error"

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file

            with open("my-favorite-pdf.pdf", "rb") as f:
                data = partition_file(
                    f,
                    aryn_api_key="MY-ARYN-API-KEY",
                    text_mode="standard_ocr",
                    table_mode="standard",
                    extract_images=True
                )
            elements = data['elements']
    """

    return _partition_file_wrapper(
        file=file,
        aryn_api_key=aryn_api_key,
        aryn_config=aryn_config,
        threshold=threshold,
        text_mode=text_mode,
        table_mode=table_mode,
        use_ocr=use_ocr,
        summarize_images=summarize_images,
        ocr_language=ocr_language,
        extract_table_structure=extract_table_structure,
        text_extraction_options=text_extraction_options,
        table_extraction_options=table_extraction_options,
        extract_images=extract_images,
        extract_image_format=extract_image_format,
        selected_pages=selected_pages,
        chunking_options=chunking_options,
        aps_url=aps_url,
        docparse_url=docparse_url,
        ssl_verify=ssl_verify,
        output_format=output_format,
        markdown_options=markdown_options,
        output_label_options=output_label_options,
        return_pdf_base64=return_pdf_base64,
        trace_id=trace_id,
        extra_headers=extra_headers,
        cancel_flag=cancel_flag,
        add_to_docset_id=add_to_docset_id,
        filename=filename,
        content_type=content_type,
    )


def _partition_file_wrapper(
    file: Union[BinaryIO, str, PathLike],
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    threshold: Optional[Union[float, Literal["auto"]]] = None,
    text_mode: Optional[str] = None,
    table_mode: Optional[str] = None,
    use_ocr: Optional[bool] = None,
    summarize_images: bool = False,
    ocr_language: Optional[str] = None,
    extract_table_structure: Optional[bool] = None,
    text_extraction_options: Optional[dict[str, Any]] = None,
    table_extraction_options: Optional[dict[str, Any]] = None,
    extract_images: bool = False,
    extract_image_format: Optional[str] = None,
    selected_pages: Optional[list[Union[list[int], int]]] = None,
    chunking_options: Optional[dict[str, Any]] = None,
    aps_url: Optional[str] = None,  # deprecated in favor of docparse_url
    docparse_url: Optional[str] = None,
    ssl_verify: bool = True,
    output_format: Optional[str] = None,
    markdown_options: Optional[dict[str, Any]] = None,
    output_label_options: Optional[dict[str, Any]] = None,
    return_pdf_base64: bool = False,
    webhook_url: Optional[str] = None,
    trace_id: Optional[str] = None,  # deprecated
    extra_headers: Optional[dict[str, str]] = None,
    cancel_flag: Optional[BoolFlag] = None,
    add_to_docset_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
):
    """Do not call this function directly. Use partition_file or partition_file_async_submit instead."""

    # If you hand me a path for the file, read it in instead of trying to send the path
    should_close = False
    try:
        if isinstance(file, (str, PathLike)):
            file = open(file, "rb")
            should_close = True
        return _partition_file_inner(
            file=file,
            aryn_api_key=aryn_api_key,
            aryn_config=aryn_config,
            threshold=threshold,
            text_mode=text_mode,
            table_mode=table_mode,
            use_ocr=use_ocr,
            summarize_images=summarize_images,
            ocr_language=ocr_language,
            extract_table_structure=extract_table_structure,
            text_extraction_options=text_extraction_options,
            table_extraction_options=table_extraction_options,
            extract_images=extract_images,
            extract_image_format=extract_image_format,
            selected_pages=selected_pages,
            chunking_options=chunking_options,
            aps_url=aps_url,
            docparse_url=docparse_url,
            ssl_verify=ssl_verify,
            output_format=output_format,
            markdown_options=markdown_options,
            output_label_options=output_label_options,
            return_pdf_base64=return_pdf_base64,
            trace_id=trace_id,
            extra_headers=extra_headers,
            cancel_flag=cancel_flag,
            webhook_url=webhook_url,
            add_to_docset_id=add_to_docset_id,
            filename=filename,
            content_type=content_type,
        )
    finally:
        if should_close and isinstance(file, BinaryIO):
            file.close()


def _partition_file_inner(
    file: BinaryIO,
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    threshold: Optional[Union[float, Literal["auto"]]] = None,
    text_mode: Optional[str] = None,
    table_mode: Optional[str] = None,
    use_ocr: Optional[bool] = None,
    summarize_images: bool = False,
    ocr_language: Optional[str] = None,
    extract_table_structure: Optional[bool] = None,
    text_extraction_options: Optional[dict[str, Any]] = None,
    table_extraction_options: Optional[dict[str, Any]] = None,
    extract_images: bool = False,
    extract_image_format: Optional[str] = None,
    selected_pages: Optional[list[Union[list[int], int]]] = None,
    chunking_options: Optional[dict[str, Any]] = None,
    aps_url: Optional[str] = None,  # deprecated in favor of docparse_url
    docparse_url: Optional[str] = None,
    ssl_verify: bool = True,
    output_format: Optional[str] = None,
    markdown_options: Optional[dict[str, Any]] = None,
    output_label_options: Optional[dict[str, Any]] = None,
    return_pdf_base64: bool = False,
    trace_id: Optional[str] = None,  # deprecated
    extra_headers: Optional[dict[str, str]] = None,
    cancel_flag: Optional[BoolFlag] = None,
    webhook_url: Optional[str] = None,
    add_to_docset_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
):
    """Do not call this function directly. Use partition_file or partition_file_async_submit instead."""

    aryn_config = _process_config(aryn_api_key, aryn_config)

    if aps_url is not None:
        if docparse_url is not None:
            logging.warning(
                '"aps_url" and "docparse_url" parameters were both set. "aps_url" is deprecated. Using "docparse_url".'
            )
        else:
            logging.warning('"aps_url" parameter is deprecated. Use "docparse_url" instead')
            docparse_url = aps_url
    if text_mode is not None and (
        use_ocr is not None or (text_extraction_options and ("ocr_text_mode" in text_extraction_options))
    ):
        logging.warning(
            '"text_mode" parameter was set. Since "use_ocr" and "ocr_text_mode" parameters are deprecated, using "text_mode".'
        )
    else:
        if use_ocr:
            ocr_text_mode = "standard"
            if text_extraction_options and ("ocr_text_mode" in text_extraction_options):
                ocr_text_mode = text_extraction_options["ocr_text_mode"]
            text_mode = f"ocr_{ocr_text_mode}"

    if table_mode is not None and extract_table_structure is not None:
        logging.warning(
            '"table_mode" parameter was set. Since "extract_table_structure" is deprecated, using "table_mode".'
        )

    if docparse_url is None:
        docparse_url = ARYN_DOCPARSE_URL
    source = "aryn-sdk"
    if extra_headers:
        source = extra_headers.get("X-Aryn-Origin", "aryn-sdk")

    options_str = _json_options(
        threshold=threshold,
        text_mode=text_mode,
        table_mode=table_mode,
        summarize_images=summarize_images,
        ocr_language=ocr_language,
        extract_table_structure=extract_table_structure,
        text_extraction_options=text_extraction_options,
        table_extraction_options=table_extraction_options,
        extract_images=extract_images,
        extract_image_format=extract_image_format,
        selected_pages=selected_pages,
        output_format=output_format,
        chunking_options=chunking_options,
        markdown_options=markdown_options,
        output_label_options=output_label_options,
        return_pdf_base64=return_pdf_base64,
        add_to_docset_id=add_to_docset_id,
        source=source,
    )

    _logger.debug(f"{options_str}")

    file_metadata_list: list[Union[BinaryIO, str]] = [file]
    if filename is not None:
        file_metadata_list.insert(0, filename)
    if content_type is not None:
        file_metadata_list.append(content_type)
        if len(file_metadata_list) == 2:
            file_metadata_list.insert(0, file.name or "upload")

    files: Mapping = {
        "options": options_str.encode("utf-8"),
        "file": tuple(file_metadata_list) if len(file_metadata_list) > 1 else file,
    }
    headers = _generate_headers(aryn_config.api_key(), webhook_url, trace_id, extra_headers)

    content = []
    partial_line = []
    in_bulk = False

    # If you run into issues VCR.py, you can apply the monkey patch described here:
    # https://github.com/kevin1024/vcrpy/issues/656#issuecomment-2492379346
    with httpx.stream("POST", docparse_url, files=files, headers=headers, verify=ssl_verify, timeout=500) as resp:
        raise_error_on_non_2xx(resp)

        for part in resp.iter_bytes():
            # A big doc could take a while; we may be asked to bail out early
            if cancel_flag and cancel_flag.get():
                resp.close()
                break

            if not part:
                continue

            content.append(part)
            if in_bulk:
                continue

            partial_line.append(part)
            if b"\n" not in part:
                continue

            these_lines = b"".join(partial_line).split(b"\n")
            partial_line = [these_lines.pop()]

            for line in these_lines:
                if line.startswith(b"  ],"):
                    in_bulk = True
                    break
                if line.startswith(b'    "T+'):
                    t = json.loads(line.decode("utf-8").removesuffix(","))
                    _logger.info(f"ArynPartitioner: {t}")

    body = b"".join(content).decode("utf-8")
    _logger.debug("Recieved data from ArynPartitioner")

    data = json.loads(body)
    assert isinstance(data, dict)
    status = data.get("status", [])
    if error := data.get("error"):
        code = data.get("status_code")
        if code is None:
            code = 429 if error.startswith("429: ") else 500
        if code == 429:
            prefix = "Limit exceeded"
        else:
            prefix = "Error partway through processing"
        _logger.info(f"Error from ArynPartitioner: {error}")
        raise PartitionError(f"{prefix}: {error}\nPartial Status:\n{status}", code)
    return data


def raise_error_on_non_2xx(resp: httpx.Response) -> None:
    if resp.status_code < 200 or resp.status_code > 299:
        resp.read()  # Try to read the reponse to get the error message
        raise httpx.HTTPStatusError(
            f"Error: status_code: {resp.status_code}, reason: {resp.text}",
            request=resp.request,
            response=resp,
        )


def _process_config(aryn_api_key: Optional[str] = None, aryn_config: Optional[ArynConfig] = None) -> ArynConfig:
    if aryn_api_key is not None:
        if aryn_config is not None:
            _logger.warning("Both aryn_api_key and aryn_config were provided. Using aryn_api_key")
        aryn_config = ArynConfig(aryn_api_key=aryn_api_key)
    if aryn_config is None:
        aryn_config = ArynConfig()
    return aryn_config


def _generate_headers(
    aryn_api_key: str,
    webhook_url: Optional[str] = None,
    trace_id: Optional[str] = None,  # deprecated
    extra_headers: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    # Start with user-supplied headers so they can't stomp official ones.
    headers = extra_headers.copy() if extra_headers else {}
    if webhook_url:
        headers["X-Aryn-Webhook"] = webhook_url
    if trace_id:
        headers["X-Aryn-Trace-ID"] = trace_id  # deprecated
    headers["Authorization"] = f"Bearer {aryn_api_key}"
    headers["User-Agent"] = f"aryn-sdk/{g_version}"
    return headers


def _json_options(
    threshold: Optional[Union[float, Literal["auto"]]] = None,
    text_mode: Optional[str] = None,
    table_mode: Optional[str] = None,
    summarize_images: bool = False,
    ocr_language: Optional[str] = None,
    extract_table_structure: Optional[bool] = None,
    text_extraction_options: Optional[dict[str, Any]] = None,
    table_extraction_options: Optional[dict[str, Any]] = None,
    extract_images: bool = False,
    extract_image_format: Optional[str] = None,
    selected_pages: Optional[list[Union[list[int], int]]] = None,
    output_format: Optional[str] = None,
    chunking_options: Optional[dict[str, Any]] = None,
    markdown_options: Optional[dict[str, Any]] = None,
    return_pdf_base64: bool = False,
    output_label_options: Optional[dict[str, Any]] = None,
    add_to_docset_id: Optional[str] = None,
    source: str = "aryn-sdk",
) -> str:
    # isn't type-checking fun
    options: dict[str, Union[float, bool, str, list[Union[list[int], int]], dict[str, Any]]] = dict()
    if threshold is not None:
        options["threshold"] = threshold
    if summarize_images:
        options["summarize_images"] = summarize_images
    if ocr_language:
        options["ocr_language"] = ocr_language
    if extract_images:
        options["extract_images"] = extract_images
    if extract_image_format:
        options["extract_image_format"] = extract_image_format
    if text_mode:
        options["text_mode"] = text_mode
    if table_mode:
        options["table_mode"] = table_mode
    if extract_table_structure is not None:
        options["extract_table_structure"] = extract_table_structure
    if text_extraction_options:
        options["text_extraction_options"] = text_extraction_options
    if table_extraction_options:
        options["table_extraction_options"] = table_extraction_options
    if selected_pages:
        options["selected_pages"] = selected_pages
    if output_format:
        options["output_format"] = output_format
    if chunking_options is not None:
        options["chunking_options"] = chunking_options
    if markdown_options:
        options["markdown_options"] = markdown_options
    if return_pdf_base64:
        options["return_pdf_base64"] = return_pdf_base64
    if output_label_options:
        options["output_label_options"] = output_label_options
    if add_to_docset_id:
        options["add_to_docset_id"] = add_to_docset_id

    options["source"] = source

    return json.dumps(options)


def partition_file_async_submit(
    file: Union[BinaryIO, str, PathLike],
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    threshold: Optional[Union[float, Literal["auto"]]] = None,
    text_mode: Optional[str] = None,
    table_mode: Optional[str] = None,
    use_ocr: Optional[bool] = None,
    summarize_images: bool = False,
    ocr_language: Optional[str] = None,
    extract_table_structure: bool = False,
    text_extraction_options: Optional[dict[str, Any]] = None,
    table_extraction_options: Optional[dict[str, Any]] = None,
    extract_images: bool = False,
    extract_image_format: Optional[str] = None,
    selected_pages: Optional[list[Union[list[int], int]]] = None,
    chunking_options: Optional[dict[str, Any]] = None,
    aps_url: Optional[str] = None,  # deprecated in favor of docparse_url
    docparse_url: Optional[str] = None,
    ssl_verify: bool = True,
    output_format: Optional[str] = None,
    markdown_options: Optional[dict[str, Any]] = None,
    output_label_options: Optional[dict[str, Any]] = None,
    trace_id: Optional[str] = None,  # deprecated
    extra_headers: Optional[dict[str, str]] = None,
    webhook_url: Optional[str] = None,
    async_submit_url: Optional[str] = None,
    add_to_docset_id: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Submits a file to be partitioned asynchronously. Meant to be used in tandem with `partition_file_async_result`.

    `partition_file_async_submit` takes the same arguments as `partition_file`, and in addition it accepts a str
    `webhook_url` argument which is a URL Aryn will send a POST request to when the task stops and an str
    `async_submit_url` argument that can be used to override where the task is submitted to.

    Set the `docparse_url` argument to the url of the synchronous endpoint, and this function will automatically
    change it to the async endpoint as long as `async_submit_url` is not set.

    For examples of usage see README.md

    Args:
        Includes All Arguments `partition_file` accepts plus those below:
        ...
        webhook_url: A URL to send a POST request to when the task is done. The resulting POST request will have a
            body like: {"done": [{"task_id": "aryn:j-47gpd3604e5tz79z1jro5fc"}]}
        async_submit_url: When set, this will override the endpoint the task is submitted to.

    Returns:
        A dictionary containing the key "task_id" the value of which can be used with the `partition_file_async_result`
        function to get the results and check the status of the async task.
    """

    if async_submit_url:
        docparse_url = async_submit_url
    elif not aps_url and not docparse_url:
        docparse_url = _convert_sync_to_async_url(ARYN_DOCPARSE_URL, "/submit", truncate=False)
    else:
        if aps_url:
            aps_url = _convert_sync_to_async_url(aps_url, "/submit", truncate=False)
        if docparse_url:
            docparse_url = _convert_sync_to_async_url(docparse_url, "/submit", truncate=False)

    return _partition_file_wrapper(
        file=file,
        aryn_api_key=aryn_api_key,
        aryn_config=aryn_config,
        threshold=threshold,
        text_mode=text_mode,
        table_mode=table_mode,
        use_ocr=use_ocr,
        summarize_images=summarize_images,
        ocr_language=ocr_language,
        extract_table_structure=extract_table_structure,
        text_extraction_options=text_extraction_options,
        table_extraction_options=table_extraction_options,
        extract_images=extract_images,
        extract_image_format=extract_image_format,
        selected_pages=selected_pages,
        chunking_options=chunking_options,
        aps_url=aps_url,
        docparse_url=docparse_url,
        ssl_verify=ssl_verify,
        output_format=output_format,
        markdown_options=markdown_options,
        output_label_options=output_label_options,
        trace_id=trace_id,
        extra_headers=extra_headers,
        webhook_url=webhook_url,
        add_to_docset_id=add_to_docset_id,
        filename=filename,
        content_type=content_type,
    )


def _convert_sync_to_async_url(url: str, prefix: str, *, truncate: bool) -> str:
    parsed_url = urlparse(url)
    assert parsed_url.path.startswith("/v1/")
    if parsed_url.path.startswith("/v1/async/submit"):
        return url
    ary = list(parsed_url)
    if truncate:
        ary[2] = f"/v1/async{prefix}"  # path
    else:
        ary[2] = f"/v1/async{prefix}{parsed_url.path[3:]}"  # path
    return urlunparse(ary)


def partition_file_async_result(
    task_id: str,
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    ssl_verify: bool = True,
    async_result_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    Get the results of an asynchronous partitioning task by task_id. Meant to be used with
    `partition_file_async_submit`.

    For examples of usage see README.md

    Raises a `PartitionTaskNotFoundError` if the not task with the task_id can be found.

    Returns:
        A dict containing "status" and "status_code". When "status" is "done", the returned dict also contains "result"
        which contains what would have been returned had `partition_file` been called directly. "status" can be "done"
        or "pending".

        Unlike `partition_file`, this function does not raise an Exception if the partitioning failed.
    """
    if not async_result_url:
        async_result_url = _convert_sync_to_async_url(ARYN_DOCPARSE_URL, "/result", truncate=True)

    aryn_config = _process_config(aryn_api_key, aryn_config)

    specific_task_url = f"{async_result_url.rstrip('/')}/{task_id}"
    headers = _generate_headers(aryn_config.api_key())
    response = httpx.get(specific_task_url, params=g_parameters, headers=headers, verify=ssl_verify)
    if response.status_code == 200:
        return {"task_status": "done", "result": response.json()}
    elif response.status_code == 202:
        return {"task_status": "pending"}
    elif response.status_code == 404:
        raise PartitionTaskNotFoundError("No such task", response.status_code)
    else:
        raise_error_on_non_2xx(response)
        raise PartitionTaskError("Unexpected response code", response.status_code)


def partition_file_async_cancel(
    task_id: str,
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    ssl_verify: bool = True,
    async_cancel_url: Optional[str] = None,
) -> None:
    """
    Cancel an asynchronous partitioning task by task_id. Meant to be used with `partition_file_async_submit`.

    Raises an exception if there is no cancellable task found with the given task_id. A task can only be successfully
    cancelled once.

    For an example of usage see README.md
    """
    if not async_cancel_url:
        async_cancel_url = _convert_sync_to_async_url(ARYN_DOCPARSE_URL, "/cancel", truncate=True)

    aryn_config = _process_config(aryn_api_key, aryn_config)

    specific_task_url = f"{async_cancel_url.rstrip('/')}/{task_id}"
    headers = _generate_headers(aryn_config.api_key())
    response = httpx.post(specific_task_url, params=g_parameters, headers=headers, verify=ssl_verify)
    if response.status_code == 200:
        return
    elif response.status_code == 404:
        raise PartitionTaskNotFoundError("No such task", response.status_code)
    else:
        raise_error_on_non_2xx(response)
        raise PartitionTaskError("Unexpected response code.", response.status_code)


def partition_file_async_list(
    *,
    aryn_api_key: Optional[str] = None,
    aryn_config: Optional[ArynConfig] = None,
    ssl_verify: bool = True,
    async_list_url: Optional[str] = None,
) -> dict[str, Any]:
    """
    List pending async tasks. For an example of usage see README.md

    Returns:
        A dict like the one below which maps task_ids to a dict containing details of the respective task.

        {
            "aryn:j-sc0v0lglkauo774pioflp4l": {
                "state": "run"
            },
            "aryn:j-b9xp7ny0eejvqvbazjhg8rn": {
                "state": "run"
            }
        }
    """
    if not async_list_url:
        async_list_url = _convert_sync_to_async_url(ARYN_DOCPARSE_URL, "/list", truncate=True)

    aryn_config = _process_config(aryn_api_key, aryn_config)

    headers = _generate_headers(aryn_config.api_key())
    response = httpx.get(async_list_url, params=g_parameters, headers=headers, verify=ssl_verify)
    raise_error_on_non_2xx(response)
    if response.status_code != 200:
        raise PartitionTaskError("Unexpected response code", response.status_code)

    result = response.json()

    tasks = result["tasks"]
    for v in tasks.values():
        v.pop("action", None)
    return tasks


def table_elem_to_html(elem: dict[str, Any], pretty: bool = False) -> Optional[str]:
    """
    Create an HTML table representing the tabular data inside the provided table element.
    If the element is not of type 'table' or doesn't contain any table data, return None instead.

    Args:
        elem: An element dict from the 'elements' field of a ``partition_file`` response.
        pretty: If True, pretty print the HTML output. Defaults to false.

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file, table_elem_to_html

            with open("partition-me.pdf", "rb") as f:
                data = partition_file(
                    f,
                    text_mode="ocr_standard",
                    extract_table_structure=True,
                    extract_images=True
                )

            # Find the first table and convert it to HTML
            html = None
            for element in data['elements']:
                if element['type'] == 'table':
                    html = table_elem_to_html(element)
                    break

    """
    if elem["type"] != "table" or elem["table"] is None:
        return None

    table = ET.Element("table")
    root = table

    table_elem = elem["table"]

    curr_row = -1
    row = None

    if table_elem["caption"] is not None:
        caption = ET.SubElement(table, "caption")
        caption.text = table_elem["caption"]

    for cell in table_elem["cells"]:
        cell_attribs = {}

        rowspan = len(cell["rows"])
        colspan = len(cell["cols"])

        if rowspan > 1:
            cell_attribs["rowspan"] = str(rowspan)
        if colspan > 1:
            cell_attribs["colspan"] = str(colspan)

        if cell["rows"][0] > curr_row:
            curr_row = cell["rows"][0]
            row = ET.SubElement(table, "tr")

        assert row is not None
        tcell = ET.SubElement(row, "th" if cell["is_header"] else "td", attrib=cell_attribs)
        tcell.text = cell["content"]

    if pretty:
        ET.indent(root)

    return ET.tostring(root, encoding="unicode")


# Heavily adapted from lib/sycamore/data/table.py::Table.to_csv()
def table_elem_to_dataframe(elem: dict) -> Optional[pd.DataFrame]:
    """
    Create a pandas DataFrame representing the tabular data inside the provided table element.
    If the element is not of type 'table' or doesn't contain any table data, return None instead.

    Args:
        elem: An element from the 'elements' field of a ``partition_file`` response.

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file, table_elem_to_dataframe

            with open("partition-me.pdf", "rb") as f:
                data = partition_file(
                    f,
                    text_mode="ocr_standard",
                    extract_table_structure=True,
                    extract_images=True
                )

            # Find the first table and convert it to a dataframe
            df = None
            for element in data['elements']:
                if element['type'] == 'table':
                    df = table_elem_to_dataframe(element)
                    break
    """

    if (elem["type"] != "table") or (elem["table"] is None):
        return None

    table = elem["table"]

    header_rows = sorted(set(row_num for cell in table["cells"] for row_num in cell["rows"] if cell["is_header"]))
    i = -1
    for i in range(len(header_rows)):
        if header_rows[i] != i:
            break
    max_header_prefix_row = i
    grid_width = table["num_cols"]
    grid_height = table["num_rows"]

    grid = np.empty([grid_height, grid_width], dtype="object")
    for cell in table["cells"]:
        if cell["is_header"] and cell["rows"][0] <= max_header_prefix_row:
            for col in cell["cols"]:
                grid[cell["rows"][0], col] = cell["content"]
            for row in cell["rows"][1:]:
                for col in cell["cols"]:
                    grid[row, col] = ""
        else:
            grid[cell["rows"][0], cell["cols"][0]] = cell["content"]
            for col in cell["cols"][1:]:
                grid[cell["rows"][0], col] = ""
            for row in cell["rows"][1:]:
                for col in cell["cols"]:
                    grid[row, col] = ""

    header = grid[: max_header_prefix_row + 1, :]
    flattened_header = []
    for npcol in header.transpose():
        flattened_header.append(" | ".join(OrderedDict.fromkeys((c for c in npcol if c != ""))))
    df = pd.DataFrame(
        grid[max_header_prefix_row + 1 :, :],
        index=None,
        columns=flattened_header if max_header_prefix_row >= 0 else None,
    )

    return df


def tables_to_pandas(data: dict) -> list[tuple[dict, Optional[pd.DataFrame]]]:
    """
    For every table element in the provided partitioning response, create a pandas
    DataFrame representing the tabular data. Return a list containing all the elements,
    with tables paired with their corresponding DataFrames.

    Args:
        data: a response from ``partition_file``

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file, tables_to_pandas

            with open("my-favorite-pdf.pdf", "rb") as f:
                data = partition_file(
                    f,
                    aryn_api_key="MY-ARYN-API-KEY",
                    text_mode="ocr_standard",
                    extract_table_structure=True,
                    extract_images=True
                )
            elts_and_dataframes = tables_to_pandas(data)

    """
    results = []
    for e in data["elements"]:
        results.append((e, table_elem_to_dataframe(e)))

    return results


def tables_to_html(data: dict) -> list[tuple[dict, Optional[str]]]:
    """
    For every table element in the provided partitioning response, create an HTML
    string representing the tabular data. Return a list containing all the elements,
    with tables paired with their corresponding HTML.

    Args:
        data: a response from ``partition_file``

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file, tables_to_html

            with open("my-favorite-pdf.pdf", "rb") as f:
                data = partition_file(
                    f,
                    aryn_api_key="MY-ARYN-API-KEY",
                    text_mode="ocr_standard",
                    extract_table_structure=True,
                    extract_images=True
                )
            elts_and_html = tables_to_html(data)
    """
    results = []
    for e in data["elements"]:
        results.append((e, table_elem_to_html(e)))

    return results


def convert_image_element(
    elem: dict, format: str = "PIL", b64encode: bool = False
) -> Optional[Union[Image.Image, bytes, str]]:
    """
    Convert an image element to a more useable format. If no format is specified,
    create a PIL Image object. If a format is specified, output the bytes of the image
    in that format. If b64encode is set to True, base64-encode the bytes and return them
    as a string.

    Args:
        elem: an image element from the 'elements' field of a ``partition_file`` response
        format: an optional format to output bytes of. Default is PIL
        b64encode: base64-encode the output bytes. Format must be set to use this

    Example:
         .. code-block:: python

            from aryn_sdk.partition import partition_file, convert_image_element

            with open("my-favorite-pdf.pdf", "rb") as f:
                data = partition_file(
                    f,
                    extract_images=True
                )
            image_elts = [e for e in data['elements'] if e['type'] == 'Image']

            pil_img = convert_image_element(image_elts[0])
            jpg_byes = convert_image_element(image_elts[1], format='JPEG')
            png_str = convert_image_element(image_elts[2], format="PNG", b64encode=True)

    """
    if b64encode and format == "PIL":
        raise ValueError("b64encode was True but format was PIL. Cannot b64-encode a PIL Image")

    if elem.get("type") != "Image":
        return None

    width = elem["properties"]["image_size"][0]
    height = elem["properties"]["image_size"][1]
    mode = elem["properties"]["image_mode"]

    raw_bytes = base64.b64decode(elem["binary_representation"])
    in_format = elem["properties"].get("image_format")

    if in_format is None:
        im = Image.frombytes(mode, (width, height), data=raw_bytes)
    else:
        in_buf = io.BytesIO(raw_bytes)
        im = Image.open(in_buf, formats=[in_format])

    if format == "PIL":
        return im

    buf = io.BytesIO()
    im.save(buf, format)

    if not b64encode:
        return buf.getvalue()
    else:
        return base64.b64encode(buf.getvalue()).decode("utf-8")

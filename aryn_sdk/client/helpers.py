"""
Functionality to add multiple files/directories to DocStore

The easy way to call this is:

r = add_docs(docset_id, pathlist)

However, it's likely that a filter is needed, as so:

f = Filter().include_glob("*.pdf")
r = add_docs(docset_id, pathlist, f)

The underlying classes can be used, too:

pdf = Filter().include_regex("[.]pdf$")
doc = Filter().include_regex("[.]docx$")
a = DocAdder(docset_id)
a.add(pathlist1, pdf).add(pathlist2, doc)
r = a.finish()
"""

import os
import re
import stat
import time
import json
import logging
import threading
from queue import Empty, Queue
from typing import Any, Optional, Union
from contextlib import suppress

from .client import Client
from .exceptions import ArynSDKException

import httpx


g_logger = logging.getLogger("DocAdder")


class Filter:
    """Uses an include pattern list and an exclude pattern list to decide
    if a given path should be allowed."""

    def __init__(self) -> None:
        self.includes = PatList()
        self.excludes = PatList()

    def include_regex(self, r: Union[str, re.Pattern]) -> "Filter":
        self.includes.add(r)
        return self

    def exclude_regex(self, r: Union[str, re.Pattern]) -> "Filter":
        self.excludes.add(r)
        return self

    def include_glob(self, g: str) -> "Filter":
        self.includes.add(glob2re(g))
        return self

    def exclude_glob(self, g: str) -> "Filter":
        self.excludes.add(glob2re(g))
        return self

    def check(self, path) -> bool:
        if self.includes and not self.includes.any_search(path):
            return False
        if self.excludes and self.excludes.any_search(path):
            return False
        return True


class DocAdder:
    """Client for DocStore to add files/directories to a DocSet.  Once
    instantiated, call add() one or more times, then call finish().  It
    may take a long time as it waits for all documents to finish."""

    def __init__(self, client: Client, docset_id: str) -> None:
        self.client = client
        self.docset_id = docset_id
        self.maxtasks = 1000
        self.tasks: dict[str, str] = {}
        self.done: dict[str, dict[str, str]] = {}

        userdata = {"TargetDocSet": docset_id}

        self.extra_headers = {
            "User-Agent": "AddDocs/0.1",
            "X-Aryn-Userdata": json.dumps(userdata),
        }

        self.submit = f"/v1/async/submit/docstore/docsets/{self.docset_id}/docs"
        self.options: dict[str, Any] = {
            "use_ocr": True,
            "extract_table_structure": True,
        }

        self.scan_q: Queue = Queue(100)
        self.doc_q: Queue = Queue(100)
        self.scan_thr = threading.Thread(target=self._dirscan_worker, name="DirScanWorker")
        self.doc_thr = threading.Thread(target=self._docstore_worker, name="AddDocsWorker")
        self.scan_thr.start()
        self.doc_thr.start()

    def add(
        self, paths: list[str], filter: Optional[Filter] = None, options: Optional[dict[str, Any]] = None
    ) -> "DocAdder":
        """Add multiple files/directories to the DocSet."""
        if filter is None:
            filter = Filter()
        if options is None:
            options = self.options
        self.scan_q.put(ScanRec(paths, filter, options))
        return self

    def finish(self) -> dict[str, dict[str, str]]:
        """Wait for all documents to finish and return map of results."""
        self.scan_q.put(None)
        self.scan_thr.join()
        self.doc_q.put(None)
        self.doc_thr.join()
        return self.done

    def empty(self) -> bool:
        """Indicate if the internal queues and state are empty."""
        return self.scan_q.empty() and self.doc_q.empty() and not self.tasks

    def progress(self) -> tuple[int, int]:
        """Return number of tasks pending and done as a tuple."""
        return len(self.tasks), len(self.done)

    def cancel_all(self) -> None:
        """This is mostly for testing."""
        for task_id in self.tasks.keys():
            self._cancel_one(task_id)

    def _dirscan_worker(self) -> None:
        while True:
            rec = self.scan_q.get()
            if rec is None:
                break
            for path in rec.paths:
                st = os.stat(path)
                if stat.S_ISDIR(st.st_mode):
                    self._dir_recurse(path, rec.filter, rec.options, 0)
                elif stat.S_ISREG(st.st_mode):
                    if rec.filter.check(path):
                        self.doc_q.put(DocRec(path, rec.options))

    def _dir_recurse(self, dir: str, filt: Filter, opts: dict[str, Any], level: int) -> None:
        if level > 80:  # kernel limits to 40 symlink resolutions per path
            raise RecursionError()
        with os.scandir(dir) as scan:
            ents = list(scan)
        ents.sort(key=lambda e: e.name)
        for ent in ents:
            if ent.is_dir():
                self._dir_recurse(ent.path, filt, opts, level + 1)
            elif ent.is_file():
                if filt.check(ent.path):
                    self.doc_q.put(DocRec(ent.path, opts))

    def _docstore_worker(self) -> None:
        qok = True
        while self.tasks or qok:
            idle = True
            while qok and (len(self.tasks) < self.maxtasks):
                try:
                    rec = self.doc_q.get_nowait()
                    if rec is None:
                        qok = False
                    else:
                        self._submit_one(rec.path, rec.options)
                        idle = False
                except Empty:
                    break
            if idle:
                time.sleep(1.0)
            self._poll_tasks()

    def _poll_tasks(self) -> None:
        nap = 5.0 / max(1, len(self.tasks))
        nap = max(0.001, min(1.0, nap))
        drops: list[str] = []
        for task_id, path in self.tasks.items():
            try:
                r = self.client._get_async_result_internal(task=task_id, extra_headers=self.extra_headers)
                if r.status_code == 202:  # still pending
                    time.sleep(nap)
                elif r.status_code == 200:  # OK
                    data = r.json()
                    doc_id = data["doc_id"]
                    g_logger.info(f"Finished {task_id} {path} {doc_id}")
                    self.done[path] = {"status": "ok", "doc_id": doc_id}
                    drops.append(task_id)
                else:
                    msg = msg_from_resp(r)
                    g_logger.info(f"Got {r.status_code} for {task_id} {msg}")
                    self.done[path] = {"status": "error", "error_response": msg}
                    drops.append(task_id)
            except (ArynSDKException, httpx.RequestError) as e:
                g_logger.warning(f"Exception for {task_id} {e}")
                self.done[path] = {"status": "error", "error_response": str(e)}
                drops.append(task_id)
        for key in drops:  # avoid modifying while iterating
            del self.tasks[key]

    def _submit_one(self, path: str, opts: dict[str, Any]) -> None:
        g_logger.info(f"Submit {path}")
        try:
            r = self.client._add_doc_async_internal(
                file=path, docset_id=self.docset_id, options=opts, extra_headers=self.extra_headers
            )
            if r.status_code == 202:  # pending
                data = r.json()
                task_id = data["task_id"]
                self.tasks[task_id] = path
                g_logger.info(f"Map {task_id} -> {path}")
            else:
                msg = msg_from_resp(r)
                g_logger.warning(f"Got {r.status_code} from {self.submit} {path} {msg}")
                self.done[path] = {"status": "error", "error_response": msg}
        except (ArynSDKException, httpx.RequestError) as e:
            g_logger.warning(f"Exception submitting {path} {e}")

    def _cancel_one(self, task_id) -> None:
        r = self.client.cancel_async_task(task=task_id, extra_headers=self.extra_headers)
        if r.status_code == 200:  # OK
            g_logger.info(f"Cancelled {task_id}")
        elif r.status_code == 404:  # not found
            g_logger.info(f"Cancel too late for {task_id}")
        else:
            g_logger.warning(f"Failed to cancel {task_id}")


def msg_from_resp(resp: httpx.Response) -> str:
    msg = f"generic {resp.status_code}"
    if resp.content.startswith(b'{"'):
        with suppress(KeyError, ValueError):
            data = resp.json()
            msg = data["error"]
    return msg


class PatList:
    """Represents a list of regular expressions to be run with search()."""

    def __init__(self) -> None:
        self.pats: list[re.Pattern] = []

    def __bool__(self) -> bool:
        return bool(self.pats)

    def add(self, r: Union[str, re.Pattern]) -> "PatList":
        if isinstance(r, re.Pattern):
            self.pats.append(r)
        else:
            self.pats.append(re.compile(r))
        return self

    def any_search(self, s: str) -> bool:
        for pat in self.pats:
            if pat.search(s):
                return True
        return False


class ScanRec:
    __slots__ = ("paths", "filter", "options")
    paths: list[str]
    filter: Filter
    options: dict[str, Any]

    def __init__(self, paths: list[str], filter: Filter, options: dict[str, Any]) -> None:
        self.paths = paths
        self.filter = filter
        self.options = options


class DocRec:
    __slots__ = ("path", "options")
    path: str
    options: dict[str, Any]

    def __init__(self, path: str, options: dict[str, Any]) -> None:
        self.path = path
        self.options = options


def add_docs(
    client: Client, docset_id: str, paths: list[str], filter: Optional[Filter] = None
) -> dict[str, dict[str, str]]:
    """
    All-in-one function to add a batch of files and directories to DocStore.
    """
    return DocAdder(client, docset_id).add(paths, filter).finish()


_stars = re.compile(r"[*]+")


def glob2re(glob_str: str) -> re.Pattern:
    """
    From a glob like *.txt make a regex suitable for re.search().
    No current support for **.
    """
    input = _stars.sub("*", glob_str)
    regex = ""
    inclass = False
    n = len(input)
    for idx in range(n):
        ch = input[idx]
        if inclass:
            regex += ch
            if ch == "]":
                inclass = False
        else:
            if ch == "*":
                regex += ".*"
            elif ch == "?":
                regex += "."
            elif ch == "[":
                if input.find("]", idx + 1) >= 0:
                    regex += "["
                    inclass = True
                else:
                    regex += r"\["
            else:
                regex += re.escape(ch)
    regex = f"^{regex}$"
    if regex.startswith("^.*"):
        regex = regex[3:]
    if regex.endswith(".*$"):
        regex = regex[:-3]
    return re.compile(regex)

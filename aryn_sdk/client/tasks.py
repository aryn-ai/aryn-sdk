import time

from typing import Generic, Optional, Type, TypeVar, TYPE_CHECKING

from .response import Response, SimpleResponse
from .exceptions import ArynSDKException

if TYPE_CHECKING:
    from aryn.client.client import Client

T = TypeVar("T")


class AsyncTask(Generic[T]):
    def __init__(
        self, client: "Client", task_id: str, method: Optional[str], path: Optional[str], response_type: Type[T]
    ) -> None:
        self.task_id = task_id
        self._method = method
        self._path = path
        self._client = client
        self._response_type = response_type

    @property
    def path(self) -> Optional[str]:
        return self._path

    @property
    def method(self) -> Optional[str]:
        return self._method

    def cancel(self) -> SimpleResponse:
        return self._client.cancel_async_task(self)

    # TODO: Figure out behavior if task is canceled
    def result(self, timeout: Optional[int] = None) -> Response[T]:
        """Returns the result of the task.

        Waits up to timeout seconds for the task to complete.
        """
        start_time = time.time()

        while True:
            res = self._client._get_async_result_internal(self)
            if res.status_code == 200:
                # Task has completed successfully.
                return Response(res, self._response_type(**res.json()))

            elif res.status_code == 202:
                # Task is still pending
                if timeout is not None and time.time() - start_time > timeout:
                    raise TimeoutError()
                time.sleep(1)

            else:
                # Task has failed. Should be unreachable.
                raise ArynSDKException(res)

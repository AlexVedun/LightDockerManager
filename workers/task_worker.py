import docker.errors
from PySide6.QtCore import QThread, Signal


class TaskWorker(QThread):
    """Runs a callable on a background thread so the Qt GUI thread never blocks."""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
        except docker.errors.NotFound:
            self.failed.emit(self.tr(
                "This item no longer exists. It may have been removed or "
                "recreated outside this application. The list has been refreshed."
            ))
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


def run_task(owner, func, *args, on_success=None, on_error=None, **kwargs):
    """Runs func(*args, **kwargs) on a background QThread.

    The worker is kept alive on `owner` (in an internal list) until it
    finishes, since nothing else would otherwise hold a reference to it.
    """
    if not hasattr(owner, "_background_workers"):
        owner._background_workers = []

    worker = TaskWorker(func, *args, **kwargs)

    def _cleanup():
        if worker in owner._background_workers:
            owner._background_workers.remove(worker)

    if on_success is not None:
        worker.succeeded.connect(on_success)
    if on_error is not None:
        worker.failed.connect(on_error)
    worker.finished.connect(_cleanup)

    owner._background_workers.append(worker)
    worker.start()
    return worker

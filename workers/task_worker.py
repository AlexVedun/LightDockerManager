import weakref

import docker.errors
from PySide6.QtCore import QThread, Signal

_ACTIVE_WORKERS = set()


class TaskWorker(QThread):
    """Runs a callable on a background thread so the Qt GUI thread never blocks."""

    succeeded = Signal(object)
    failed = Signal(str)
    not_found = Signal(str)

    def __init__(self, func, *args, parent=None, **kwargs):
        super().__init__(parent)
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = self._func(*self._args, **self._kwargs)
        except docker.errors.NotFound:
            self.not_found.emit(self.tr(
                "This item no longer exists. It may have been removed or "
                "recreated outside this application. The list has been refreshed."
            ))
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.succeeded.emit(result)


def run_task(owner, func, *args, on_success=None, on_error=None, on_not_found=None, on_finished=None,
             track_action=False, **kwargs):
    """Runs func(*args, **kwargs) on a background QThread.

    The worker is kept alive on `owner` (in an internal list) until it
    finishes, since nothing else would otherwise hold a reference to it.

    A stale-item error (the target was removed or recreated outside this app)
    is routed to `on_not_found` when given, falling back to `on_error`
    otherwise, so existing callers keep working unchanged.
    """
    if not hasattr(owner, "_background_workers"):
        owner._background_workers = []

    worker = TaskWorker(func, *args, **kwargs)

    owner_ref = weakref.ref(owner)

    def _cleanup():
        _ACTIVE_WORKERS.discard(worker)
        live_owner = owner_ref()
        if live_owner is not None and worker in getattr(live_owner, "_background_workers", ()):
            live_owner._background_workers.remove(worker)
        try:
            if on_finished is not None and live_owner is not None:
                on_finished()
        finally:
            if track_action and live_owner is not None:
                live_owner.action_finished.emit()

    if on_success is not None:
        worker.succeeded.connect(on_success)
    if on_error is not None:
        worker.failed.connect(on_error)
    if on_not_found is not None:
        worker.not_found.connect(on_not_found)
    elif on_error is not None:
        worker.not_found.connect(on_error)
    worker.finished.connect(_cleanup)

    _ACTIVE_WORKERS.add(worker)
    owner._background_workers.append(worker)
    if track_action:
        owner.action_started.emit()
    worker.start()
    return worker


def run_bulk_task(owner, tasks, on_finished, track_action=False):
    """Runs each zero-arg callable in `tasks` sequentially on background threads.

    Calls on_finished(errors, stale) once every task has completed. `errors`
    is the list of error messages collected from failed tasks; `stale` is the
    list of messages from tasks whose target no longer existed (removed or
    recreated outside this app) - kept separate so callers can report those
    unobtrusively instead of as hard errors.
    """
    errors = []
    stale = []
    remaining = list(tasks)
    if track_action:
        owner.action_started.emit()

    def _run_next():
        if not remaining:
            try:
                on_finished(errors, stale)
            finally:
                if track_action:
                    owner.action_finished.emit()
            return
        task = remaining.pop(0)

        run_task(
            owner,
            task,
            on_error=errors.append,
            on_not_found=stale.append,
            on_finished=_run_next,
        )

    _run_next()

from PySide6.QtWidgets import QApplication

from workers.task_worker import TaskWorker, run_task

QApplication.instance() or QApplication([])


def _pump_events(worker, timeout_ms=2000):
    worker.wait(timeout_ms)
    for _ in range(50):
        QApplication.processEvents()


def test_run_emits_succeeded_with_result():
    worker = TaskWorker(lambda a, b: a + b, 2, 3)
    results = []
    worker.succeeded.connect(results.append)

    worker.run()

    assert results == [5]


def test_run_emits_failed_with_error_message_on_exception():
    def boom():
        raise RuntimeError("kaboom")

    worker = TaskWorker(boom)
    errors = []
    worker.failed.connect(errors.append)

    worker.run()

    assert errors == ["kaboom"]


def test_run_passes_kwargs_through():
    worker = TaskWorker(lambda a, b=None: (a, b), 1, b=2)
    results = []
    worker.succeeded.connect(results.append)

    worker.run()

    assert results == [(1, 2)]


class _Owner:
    pass


def test_run_task_keeps_worker_alive_and_cleans_up_on_finish():
    owner = _Owner()
    results = []

    worker = run_task(owner, lambda: 42, on_success=results.append)
    assert worker in owner._background_workers

    _pump_events(worker)

    assert results == [42]
    assert worker not in owner._background_workers


def test_run_task_reports_error_via_on_error():
    owner = _Owner()
    errors = []

    def boom():
        raise ValueError("bad")

    worker = run_task(owner, boom, on_error=errors.append)
    _pump_events(worker)

    assert errors == ["bad"]

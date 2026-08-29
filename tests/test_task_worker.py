from PySide6.QtWidgets import QApplication

import time

from workers.task_worker import TaskWorker, run_bulk_task, run_task

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


def _pump_until(condition, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return
    raise AssertionError("condition was not met in time")


def test_run_bulk_task_runs_every_task_and_reports_no_errors():
    owner = _Owner()
    calls = []
    finished = []

    tasks = [lambda i=i: calls.append(i) for i in range(3)]
    run_bulk_task(owner, tasks, finished.append)

    _pump_until(lambda: finished)

    assert calls == [0, 1, 2]
    assert finished == [[]]


def test_run_bulk_task_collects_errors_but_keeps_going():
    owner = _Owner()
    finished = []

    def boom():
        raise ValueError("bad")

    tasks = [lambda: 1, boom, lambda: 2]
    run_bulk_task(owner, tasks, finished.append)

    _pump_until(lambda: finished)

    assert finished == [["bad"]]

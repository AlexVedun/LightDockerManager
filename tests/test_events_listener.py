from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from docker_services.events_listener import DockerEventsListener

QApplication.instance() or QApplication([])


def test_run_emits_data_changed_for_known_event_types():
    client = MagicMock()
    client.events.return_value = [
        {"Type": "container", "status": "start"},
        {"Type": "image", "status": "pull"},
        {"Type": "unknown-type", "status": "noop"},
    ]

    listener = DockerEventsListener(client)
    received = []
    listener.data_changed.connect(received.append)

    listener.run()

    assert received == ["containers", "images"]


def test_stop_closes_stream_if_present():
    client = MagicMock()
    listener = DockerEventsListener(client)
    stream = MagicMock()
    listener._stream = stream

    listener.stop()

    stream.close.assert_called_once()
    assert listener._stopped is True


def test_connection_lost_emitted_on_unexpected_error():
    client = MagicMock()
    client.events.side_effect = RuntimeError("boom")

    listener = DockerEventsListener(client)
    errors = []
    listener.connection_lost.connect(errors.append)

    listener.run()

    assert errors == ["boom"]


def test_connection_lost_not_emitted_after_stop():
    client = MagicMock()
    client.events.side_effect = RuntimeError("boom")

    listener = DockerEventsListener(client)
    listener._stopped = True
    errors = []
    listener.connection_lost.connect(errors.append)

    listener.run()

    assert errors == []

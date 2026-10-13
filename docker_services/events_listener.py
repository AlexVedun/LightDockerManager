import threading

from PySide6.QtCore import QThread, Signal

EVENT_TYPE_MAP = {
    "container": "containers",
    "image": "images",
    "volume": "volumes",
    "network": "networks",
}

REFRESH_ACTIONS = {
    "container": {
        "create", "destroy", "die", "kill", "oom", "pause", "rename",
        "restart", "start", "stop", "unpause", "update",
    },
    "image": {"delete", "import", "load", "pull", "tag", "untag"},
    "volume": {"create", "destroy"},
    "network": {"create", "connect", "destroy", "disconnect", "remove"},
}


class DockerEventsListener(QThread):
    """Streams docker events and emits which entity type changed."""

    data_changed = Signal(str)
    connection_lost = Signal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client
        self._stream = None
        self._stopped = False
        self._lock = threading.Lock()

    def stop(self):
        with self._lock:
            self._stopped = True
            if self._stream is not None:
                try:
                    self._stream.close()
                except Exception:
                    pass

    def run(self):
        with self._lock:
            if self._stopped:
                return
            try:
                self._stream = self.client.events(decode=True)
            except Exception as exc:
                self.connection_lost.emit(str(exc))
                return

        try:
            for event in self._stream:
                docker_type = event.get("Type")
                entity_type = EVENT_TYPE_MAP.get(docker_type)
                action = event.get("Action") or event.get("status")
                if entity_type and action in REFRESH_ACTIONS[docker_type]:
                    self.data_changed.emit(entity_type)
        except Exception as exc:
            if not self._stopped:
                self.connection_lost.emit(str(exc))

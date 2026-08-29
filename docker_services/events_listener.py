from PySide6.QtCore import QThread, Signal

EVENT_TYPE_MAP = {
    "container": "containers",
    "image": "images",
    "volume": "volumes",
    "network": "networks",
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

    def stop(self):
        self._stopped = True
        if self._stream is not None:
            try:
                self._stream.close()
            except Exception:
                pass

    def run(self):
        try:
            self._stream = self.client.events(decode=True)
            for event in self._stream:
                entity_type = EVENT_TYPE_MAP.get(event.get("Type"))
                if entity_type:
                    self.data_changed.emit(entity_type)
        except Exception as exc:
            if not self._stopped:
                self.connection_lost.emit(str(exc))

import docker


class ConnectionManager:
    """Holds the active docker-py client used by the UI."""

    def __init__(self):
        self._client = None
        self.mode = None
        self.error = None

    def connect_local(self):
        try:
            client = docker.from_env()
            client.ping()
        except Exception as exc:
            self._client = None
            self.mode = None
            self.error = str(exc)
            raise

        self._client = client
        self.mode = "local"
        self.error = None

    @property
    def client(self):
        return self._client

    def is_connected(self):
        return self._client is not None

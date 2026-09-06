import docker

# docker-py's default (60s) is a read timeout per HTTP call, including how
# long a streaming response (e.g. a volume archive read/write during volume
# transfer) may sit idle between chunks. A transfer piping local reads
# straight into a slow remote write (e.g. over SSH on Wi-Fi) can easily go
# quiet on one side for longer than that while the other side catches up, so
# clients get a much more generous timeout everywhere.
CLIENT_TIMEOUT_SECONDS = 1800


class ConnectionManager:
    """Holds the active docker-py client used by the UI."""

    def __init__(self):
        self._client = None
        self.mode = None
        self.error = None

    def connect_local(self):
        try:
            client = docker.from_env(timeout=CLIENT_TIMEOUT_SECONDS)
            client.ping()
        except Exception as exc:
            self._client = None
            self.mode = None
            self.error = str(exc)
            raise

        self._client = client
        self.mode = "local"
        self.error = None

    def connect_remote(self, profile):
        base_url = f"ssh://{profile['user']}@{profile['host']}:{profile.get('port', 22)}"
        try:
            client = docker.DockerClient(base_url=base_url, use_ssh_client=True, timeout=CLIENT_TIMEOUT_SECONDS)
            client.ping()
        except Exception as exc:
            self._client = None
            self.mode = None
            self.error = str(exc)
            raise

        self._client = client
        self.mode = f"remote:{profile['name']}"
        self.error = None

    @property
    def client(self):
        return self._client

    def is_connected(self):
        return self._client is not None

from unittest.mock import MagicMock

from connection import manager as manager_module
from connection.manager import ConnectionManager


def test_connect_local_sets_client_and_mode(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(manager_module.docker, "from_env", lambda: fake_client)

    cm = ConnectionManager()
    cm.connect_local()

    assert cm.client is fake_client
    assert cm.mode == "local"
    assert cm.is_connected() is True
    fake_client.ping.assert_called_once()


def test_connect_local_failure_clears_state(monkeypatch):
    def boom():
        raise ConnectionError("no daemon")

    monkeypatch.setattr(manager_module.docker, "from_env", boom)

    cm = ConnectionManager()
    try:
        cm.connect_local()
    except ConnectionError:
        pass

    assert cm.client is None
    assert cm.mode is None
    assert cm.error == "no daemon"


def test_connect_remote_builds_ssh_url(monkeypatch):
    fake_client = MagicMock()
    captured = {}

    def fake_docker_client(base_url, use_ssh_client):
        captured["base_url"] = base_url
        captured["use_ssh_client"] = use_ssh_client
        return fake_client

    monkeypatch.setattr(manager_module.docker, "DockerClient", fake_docker_client)

    cm = ConnectionManager()
    cm.connect_remote({"name": "Laptop", "host": "192.168.1.50", "user": "alex", "port": 2222})

    assert captured["base_url"] == "ssh://alex@192.168.1.50:2222"
    assert captured["use_ssh_client"] is True
    assert cm.mode == "remote:Laptop"
    assert cm.client is fake_client


def test_connect_remote_defaults_port_22(monkeypatch):
    captured = {}

    def fake_docker_client(base_url, use_ssh_client):
        captured["base_url"] = base_url
        return MagicMock()

    monkeypatch.setattr(manager_module.docker, "DockerClient", fake_docker_client)

    cm = ConnectionManager()
    cm.connect_remote({"name": "Laptop", "host": "host", "user": "u"})

    assert captured["base_url"] == "ssh://u@host:22"

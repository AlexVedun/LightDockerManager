from unittest.mock import MagicMock, PropertyMock

import docker.errors

from docker_services import containers as containers_service


def make_container(name="web", status="running", tags=None, ports=None):
    container = MagicMock()
    container.id = f"id-{name}"
    container.name = name
    container.status = status
    container.image.tags = tags if tags is not None else ["nginx:latest"]
    container.image.short_id = "sha256:abc123"
    container.attrs = {"NetworkSettings": {"Ports": ports or {}}}
    return container


def test_list_containers_formats_rows():
    client = MagicMock()
    client.containers.list.return_value = [make_container()]

    rows = containers_service.list_containers(client)

    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "web"
    assert row["image"] == "nginx:latest"
    assert row["status"] == "running"
    assert row["ports"] == ""
    client.containers.list.assert_called_once_with(all=True)


def test_list_containers_falls_back_to_short_id_without_tags():
    client = MagicMock()
    client.containers.list.return_value = [make_container(tags=[])]

    rows = containers_service.list_containers(client)

    assert rows[0]["image"] == "sha256:abc123"


def test_list_containers_formats_published_ports():
    client = MagicMock()
    ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
    client.containers.list.return_value = [make_container(ports=ports)]

    rows = containers_service.list_containers(client)

    assert rows[0]["ports"] == "0.0.0.0:8080->80/tcp"


def test_list_containers_formats_unpublished_ports():
    client = MagicMock()
    ports = {"80/tcp": None}
    client.containers.list.return_value = [make_container(ports=ports)]

    rows = containers_service.list_containers(client)

    assert rows[0]["ports"] == "80/tcp"


def test_list_containers_skips_container_whose_image_vanished():
    client = MagicMock()
    gone = make_container(name="gone")
    type(gone).image = PropertyMock(side_effect=docker.errors.NotFound("no such image"))
    client.containers.list.return_value = [gone, make_container(name="web")]

    rows = containers_service.list_containers(client)

    assert [row["name"] for row in rows] == ["web"]


def test_actions_delegate_to_container_methods():
    container = make_container()

    containers_service.start(container)
    container.start.assert_called_once()

    containers_service.stop(container)
    container.stop.assert_called_once()

    containers_service.restart(container)
    container.restart.assert_called_once()

    containers_service.pause(container)
    container.pause.assert_called_once()

    containers_service.unpause(container)
    container.unpause.assert_called_once()

    containers_service.remove(container, force=True)
    container.remove.assert_called_once_with(force=True)

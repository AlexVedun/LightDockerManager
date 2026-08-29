from unittest.mock import MagicMock

import docker.errors
import pytest

from docker_services import volume_transfer


def make_client(image_present=True):
    client = MagicMock()
    if image_present:
        client.images.get.return_value = MagicMock()
    else:
        client.images.get.side_effect = docker.errors.ImageNotFound("not found")
    return client


def test_transfer_volume_happy_path_streams_archive_between_containers():
    source_client = make_client()
    dest_client = make_client()

    source_container = MagicMock()
    source_container.get_archive.return_value = (iter([b"chunk1", b"chunk2"]), {"size": 12})
    source_client.containers.create.return_value = source_container

    dest_container = MagicMock()
    dest_client.containers.create.return_value = dest_container

    volume_transfer.transfer_volume(source_client, "src-vol", dest_client, "dst-vol")

    dest_client.volumes.create.assert_called_once_with(name="dst-vol")

    source_client.containers.create.assert_called_once_with(
        volume_transfer.HELPER_IMAGE, "true", volumes={"src-vol": {"bind": "/data", "mode": "ro"}}
    )
    dest_client.containers.create.assert_called_once_with(
        volume_transfer.HELPER_IMAGE, "true", volumes={"dst-vol": {"bind": "/data", "mode": "rw"}}
    )

    source_container.get_archive.assert_called_once_with("/data/.")
    stream_arg = dest_container.put_archive.call_args[0][1]
    assert list(stream_arg) == [b"chunk1", b"chunk2"]
    assert dest_container.put_archive.call_args[0][0] == "/data"

    source_container.remove.assert_called_once_with(force=True)
    dest_container.remove.assert_called_once_with(force=True)


def test_transfer_volume_pulls_missing_helper_image():
    source_client = make_client(image_present=False)
    dest_client = make_client()
    source_client.containers.create.return_value.get_archive.return_value = (iter([]), {"size": 0})

    volume_transfer.transfer_volume(source_client, "src-vol", dest_client, "dst-vol")

    source_client.images.pull.assert_called_once_with(volume_transfer.HELPER_IMAGE)


def test_transfer_volume_cleans_up_containers_on_failure():
    source_client = make_client()
    dest_client = make_client()

    source_container = MagicMock()
    source_container.get_archive.return_value = (iter([b"chunk"]), {"size": 5})
    source_client.containers.create.return_value = source_container

    dest_container = MagicMock()
    dest_container.put_archive.side_effect = RuntimeError("network blip")
    dest_client.containers.create.return_value = dest_container

    with pytest.raises(RuntimeError):
        volume_transfer.transfer_volume(source_client, "src-vol", dest_client, "dst-vol")

    dest_container.remove.assert_called_once_with(force=True)
    source_container.remove.assert_called_once_with(force=True)


def test_transfer_volume_reports_progress():
    source_client = make_client()
    dest_client = make_client()
    source_client.containers.create.return_value.get_archive.return_value = (iter([b"x"]), {"size": 1})

    messages = []
    volume_transfer.transfer_volume(source_client, "src-vol", dest_client, "dst-vol", log=messages.append)

    assert any("completed successfully" in m for m in messages)

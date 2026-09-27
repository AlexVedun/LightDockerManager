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
    client.containers.create.return_value.exec_run.return_value = (0, b"0\t/data\n")
    return client


def test_transfer_volume_happy_path_streams_archive_between_containers():
    source_client = make_client()
    dest_client = make_client()

    source_container = MagicMock()
    source_container.get_archive.return_value = (iter([b"chunk1", b"chunk2"]), {"size": 12})
    source_container.exec_run.return_value = (0, b"0\t/data\n")
    source_client.containers.create.return_value = source_container

    dest_container = MagicMock()
    dest_client.containers.create.return_value = dest_container

    volume_transfer.transfer_volume(source_client, "src-vol", dest_client, "dst-vol")

    dest_client.volumes.create.assert_called_once_with(name="dst-vol")

    source_client.containers.create.assert_called_once_with(
        volume_transfer.HELPER_IMAGE, ["sleep", "3600"], volumes={"src-vol": {"bind": "/data", "mode": "ro"}}
    )
    dest_client.containers.create.assert_called_once_with(
        volume_transfer.HELPER_IMAGE, "true", volumes={"dst-vol": {"bind": "/data", "mode": "rw"}}
    )

    source_container.start.assert_called_once()
    source_container.exec_run.assert_called_once_with(["du", "-sk", "/data"])
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
    source_container.exec_run.return_value = (0, b"0\t/data\n")
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


def test_transfer_volume_reports_progress_against_measured_size():
    source_client = make_client()
    dest_client = make_client()
    source_container = source_client.containers.create.return_value
    source_container.exec_run.return_value = (0, b"10\t/data\n")  # 10 KB
    source_container.get_archive.return_value = (iter([b"x" * 5120, b"x" * 5120]), {"size": 1})
    dest_container = dest_client.containers.create.return_value
    dest_container.put_archive.side_effect = lambda path, data: list(data)

    events = []
    volume_transfer.transfer_volume(
        source_client, "src-vol", dest_client, "dst-vol", progress=lambda transferred, total: events.append((transferred, total))
    )

    assert events[0] == (0, 10240)
    assert events[-1] == (10240, 10240)


def test_measure_size_returns_none_when_du_fails():
    container = MagicMock()
    container.exec_run.return_value = (1, b"du: /data: Permission denied\n")

    assert volume_transfer._measure_size(container) is None


def test_measure_size_returns_none_on_unexpected_output():
    container = MagicMock()
    container.exec_run.return_value = (0, b"not a number\n")

    assert volume_transfer._measure_size(container) is None


def test_export_volume_writes_archive_to_file(tmp_path):
    client = make_client()
    container = client.containers.create.return_value
    container.exec_run.return_value = (0, b"2\t/data\n")
    container.get_archive.return_value = (iter([b"first", b"second"]), {"size": 11})
    target = tmp_path / "src-vol.tar"
    events = []

    volume_transfer.export_volume(
        client,
        "src-vol",
        target,
        progress=lambda transferred, total: events.append((transferred, total)),
    )

    assert target.read_bytes() == b"firstsecond"
    assert events[0] == (0, 2048)
    assert events[-1] == (11, 2048)
    container.remove.assert_called_once_with(force=True)
    assert list(tmp_path.glob("*.part")) == []


def test_export_volume_keeps_existing_file_when_stream_fails(tmp_path):
    client = make_client()
    container = client.containers.create.return_value
    container.exec_run.return_value = (0, b"1\t/data\n")

    def broken_stream():
        yield b"partial"
        raise RuntimeError("stream failed")

    container.get_archive.return_value = (broken_stream(), {"size": 7})
    target = tmp_path / "src-vol.tar"
    target.write_bytes(b"old archive")

    with pytest.raises(RuntimeError, match="stream failed"):
        volume_transfer.export_volume(client, "src-vol", target)

    assert target.read_bytes() == b"old archive"
    assert list(tmp_path.glob("*.part")) == []


def test_import_volume_creates_new_volume_and_streams_archive(tmp_path):
    client = make_client()
    client.volumes.get.side_effect = docker.errors.NotFound("missing")
    container = client.containers.create.return_value
    container.put_archive.side_effect = lambda path, chunks: list(chunks)
    archive = tmp_path / "restored-vol.tar"
    archive.write_bytes(b"archive contents")
    events = []

    volume_transfer.import_volume(
        client,
        "restored-vol",
        archive,
        progress=lambda transferred, total: events.append((transferred, total)),
    )

    client.volumes.create.assert_called_once_with(name="restored-vol")
    container.exec_run.assert_not_called()
    container.put_archive.assert_called_once()
    assert events[0] == (0, len(b"archive contents"))
    assert events[-1] == (len(b"archive contents"), len(b"archive contents"))
    container.remove.assert_called_once_with(force=True)


def test_import_volume_clears_existing_volume_when_overwrite_is_confirmed(tmp_path):
    client = make_client()
    container = client.containers.create.return_value
    container.exec_run.return_value = (0, b"")
    container.put_archive.side_effect = lambda path, chunks: list(chunks)
    archive = tmp_path / "existing.tar"
    archive.write_bytes(b"archive")

    volume_transfer.import_volume(client, "existing", archive, overwrite=True)

    client.volumes.create.assert_not_called()
    container.exec_run.assert_called_once_with(["sh", "-c", "find /data -mindepth 1 -delete"])
    container.put_archive.assert_called_once()


def test_import_volume_refuses_existing_volume_without_overwrite(tmp_path):
    client = make_client()
    archive = tmp_path / "existing.tar"
    archive.write_bytes(b"archive")

    with pytest.raises(volume_transfer.VolumeAlreadyExistsError):
        volume_transfer.import_volume(client, "existing", archive)

    client.containers.create.assert_not_called()


def test_import_volume_checks_archive_before_clearing_existing_volume(tmp_path):
    client = make_client()

    with pytest.raises(FileNotFoundError):
        volume_transfer.import_volume(client, "existing", tmp_path / "missing.tar", overwrite=True)

    client.volumes.get.assert_not_called()
    client.containers.create.assert_not_called()

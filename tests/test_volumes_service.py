from unittest.mock import MagicMock

from docker_services import volumes as volumes_service


def make_volume(name="data", driver="local", mountpoint="/var/lib/docker/volumes/data/_data"):
    volume = MagicMock()
    volume.name = name
    volume.attrs = {"Driver": driver, "Mountpoint": mountpoint}
    return volume


def make_container(mounts):
    container = MagicMock()
    container.attrs = {"Mounts": mounts}
    return container


def test_list_volumes_marks_used_by_container_mount():
    client = MagicMock()
    client.volumes.list.return_value = [make_volume(name="used-vol"), make_volume(name="free-vol")]
    client.containers.list.return_value = [
        make_container([{"Type": "volume", "Name": "used-vol"}])
    ]
    client.df.return_value = {"Volumes": []}

    rows = volumes_service.list_volumes(client)

    used_row = next(r for r in rows if r["name"] == "used-vol")
    free_row = next(r for r in rows if r["name"] == "free-vol")
    assert used_row["used"] is True
    assert free_row["used"] is False


def test_list_volumes_reads_size_from_df():
    client = MagicMock()
    client.volumes.list.return_value = [make_volume(name="data")]
    client.containers.list.return_value = []
    client.df.return_value = {"Volumes": [{"Name": "data", "UsageData": {"Size": 4096, "RefCount": 0}}]}

    rows = volumes_service.list_volumes(client)

    assert rows[0]["size"] == 4096


def test_list_volumes_handles_df_failure_gracefully():
    client = MagicMock()
    client.volumes.list.return_value = [make_volume(name="data")]
    client.containers.list.return_value = []
    client.df.side_effect = Exception("boom")

    rows = volumes_service.list_volumes(client)

    assert rows[0]["size"] is None


def test_remove_and_prune_delegate():
    volume = make_volume()
    volumes_service.remove(volume, force=True)
    volume.remove.assert_called_once_with(force=True)

    client = MagicMock()
    volumes_service.prune(client)
    client.volumes.prune.assert_called_once()

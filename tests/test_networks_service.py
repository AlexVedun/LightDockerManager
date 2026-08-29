from unittest.mock import MagicMock

from docker_services import networks as networks_service


def make_network(name="bridge", driver="bridge", scope="local", containers=None):
    network = MagicMock()
    network.name = name
    network.attrs = {"Driver": driver, "Scope": scope, "Containers": containers or {}}
    return network


def test_list_networks_marks_used_and_lists_container_names():
    client = MagicMock()
    connected = {"abc123": {"Name": "web"}}
    client.networks.list.return_value = [
        make_network(name="app-net", containers=connected),
        make_network(name="empty-net"),
    ]

    rows = networks_service.list_networks(client)

    used_row = next(r for r in rows if r["name"] == "app-net")
    free_row = next(r for r in rows if r["name"] == "empty-net")
    assert used_row["used"] is True
    assert used_row["containers"] == "web"
    assert free_row["used"] is False
    assert free_row["containers"] == ""


def test_remove_connect_disconnect_prune_delegate():
    network = make_network()
    container = MagicMock()

    networks_service.remove(network)
    network.remove.assert_called_once()

    networks_service.connect(network, container)
    network.connect.assert_called_once_with(container)

    networks_service.disconnect(network, container)
    network.disconnect.assert_called_once_with(container)

    client = MagicMock()
    networks_service.prune(client)
    client.networks.prune.assert_called_once()

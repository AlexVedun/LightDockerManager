def list_networks(client):
    rows = []
    for network in client.networks.list():
        connected = network.attrs.get("Containers") or {}
        names = [info.get("Name", cid[:12]) for cid, info in connected.items()]
        rows.append({
            "name": network.name,
            "driver": network.attrs.get("Driver"),
            "scope": network.attrs.get("Scope"),
            "containers": ", ".join(names),
            "used": bool(connected),
            "network": network,
        })
    return rows


def remove(network):
    network.remove()


def connect(network, container):
    network.connect(container)


def disconnect(network, container):
    network.disconnect(container)


def prune(client):
    return client.networks.prune()

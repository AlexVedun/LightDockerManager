def list_volumes(client):
    used_names = _used_volume_names(client)
    sizes = _volume_sizes(client)

    rows = []
    for volume in client.volumes.list():
        rows.append({
            "name": volume.name,
            "driver": volume.attrs.get("Driver"),
            "mountpoint": volume.attrs.get("Mountpoint"),
            "used": volume.name in used_names,
            "size": sizes.get(volume.name),
            "volume": volume,
        })
    return rows


def _used_volume_names(client):
    used = set()
    for container in client.containers.list(all=True):
        for mount in container.attrs.get("Mounts") or []:
            if mount.get("Type") == "volume" and mount.get("Name"):
                used.add(mount["Name"])
    return used


def _volume_sizes(client):
    try:
        df = client.df()
    except Exception:
        return {}

    sizes = {}
    for entry in df.get("Volumes") or []:
        usage = entry.get("UsageData") or {}
        size = usage.get("Size")
        if size is not None and size >= 0:
            sizes[entry.get("Name")] = size
    return sizes


def remove(volume, force=False):
    volume.remove(force=force)


def prune(client):
    return client.volumes.prune()

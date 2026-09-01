import docker.errors


def list_containers(client):
    """Return formatted rows for the containers table."""
    rows = []
    for container in client.containers.list(all=True, ignore_removed=True):
        try:
            image_tags = container.image.tags
            image_name = image_tags[0] if image_tags else container.image.short_id
        except docker.errors.NotFound:
            continue

        rows.append({
            "id": container.id,
            "name": container.name,
            "image": image_name,
            "status": container.status,
            "ports": _format_ports(container.attrs.get("NetworkSettings", {}).get("Ports") or {}),
            "container": container,
        })
    return rows


def _format_ports(ports):
    parts = []
    for container_port, bindings in ports.items():
        if not bindings:
            parts.append(container_port)
            continue
        for binding in bindings:
            host_ip = binding.get("HostIp") or ""
            host_port = binding.get("HostPort") or ""
            parts.append(f"{host_ip}:{host_port}->{container_port}")
    return ", ".join(parts)


def start(container):
    container.start()


def stop(container):
    container.stop()


def restart(container):
    container.restart()


def pause(container):
    container.pause()


def unpause(container):
    container.unpause()


def remove(container, force=False):
    container.remove(force=force)

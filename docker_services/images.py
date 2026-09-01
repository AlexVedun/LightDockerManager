def list_images(client):
    containers = client.containers.list(all=True, ignore_removed=True)
    used_ids = {c.attrs.get("Image") for c in containers}

    rows = []
    for image in client.images.list():
        rows.append({
            "id": image.short_id,
            "tags": ", ".join(image.tags) if image.tags else "<none>",
            "size": image.attrs.get("Size"),
            "created": image.attrs.get("Created"),
            "used": image.id in used_ids,
            "image": image,
        })
    return rows


def pull(client, repo_tag):
    client.images.pull(repo_tag)


def remove(image, force=False):
    image.remove(force=force)


def prune(client):
    return client.images.prune()

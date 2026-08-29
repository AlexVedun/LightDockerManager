from unittest.mock import MagicMock

from docker_services import images as images_service


def make_image(image_id="sha256:img1", tags=None, size=1234, created="2024-01-01T00:00:00Z"):
    image = MagicMock()
    image.id = image_id
    image.short_id = image_id[:12]
    image.tags = tags if tags is not None else ["nginx:latest"]
    image.attrs = {"Size": size, "Created": created}
    return image


def make_container(image_id="sha256:img1"):
    container = MagicMock()
    container.attrs = {"Image": image_id}
    return container


def test_list_images_marks_used_image():
    client = MagicMock()
    used_image = make_image(image_id="sha256:used")
    unused_image = make_image(image_id="sha256:unused", tags=["redis:7"])
    client.images.list.return_value = [used_image, unused_image]
    client.containers.list.return_value = [make_container(image_id="sha256:used")]

    rows = images_service.list_images(client)

    used_row = next(r for r in rows if r["tags"] == "nginx:latest")
    unused_row = next(r for r in rows if r["tags"] == "redis:7")
    assert used_row["used"] is True
    assert unused_row["used"] is False


def test_list_images_falls_back_to_none_label_without_tags():
    client = MagicMock()
    client.images.list.return_value = [make_image(tags=[])]
    client.containers.list.return_value = []

    rows = images_service.list_images(client)

    assert rows[0]["tags"] == "<none>"


def test_pull_delegates_to_client():
    client = MagicMock()
    images_service.pull(client, "nginx:latest")
    client.images.pull.assert_called_once_with("nginx:latest")


def test_remove_and_prune_delegate():
    image = make_image()
    images_service.remove(image, force=True)
    image.remove.assert_called_once_with(force=True)

    client = MagicMock()
    images_service.prune(client)
    client.images.prune.assert_called_once()

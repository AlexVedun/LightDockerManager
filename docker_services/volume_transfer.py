import docker.errors

HELPER_IMAGE = "alpine:latest"
MOUNT_PATH = "/data"


def transfer_volume(source_client, source_volume_name, dest_client, dest_volume_name, log=lambda msg: None):
    """Copy the contents of a volume from one Docker host to another.

    Both clients may point at the same daemon or at different ones (e.g. local
    and a remote SSH connection); the tar stream is piped directly between the
    two API calls without buffering the whole volume in memory.
    """
    log(f"Проверка вспомогательного образа {HELPER_IMAGE} на источнике...")
    _ensure_image(source_client, log)
    log(f"Проверка вспомогательного образа {HELPER_IMAGE} на назначении...")
    _ensure_image(dest_client, log)

    log(f"Создание целевого volume \"{dest_volume_name}\" (если не существует)...")
    dest_client.volumes.create(name=dest_volume_name)

    log("Создание вспомогательного контейнера на источнике...")
    source_container = source_client.containers.create(
        HELPER_IMAGE,
        "true",
        volumes={source_volume_name: {"bind": MOUNT_PATH, "mode": "ro"}},
    )
    try:
        log("Создание вспомогательного контейнера на назначении...")
        dest_container = dest_client.containers.create(
            HELPER_IMAGE,
            "true",
            volumes={dest_volume_name: {"bind": MOUNT_PATH, "mode": "rw"}},
        )
        try:
            log(f"Чтение содержимого volume \"{source_volume_name}\"...")
            stream, stat = source_container.get_archive(f"{MOUNT_PATH}/.")
            log(f"Запись содержимого в volume \"{dest_volume_name}\" (~{stat.get('size', '?')} байт)...")
            dest_container.put_archive(MOUNT_PATH, stream)
            log("Перенос завершён успешно.")
        finally:
            dest_container.remove(force=True)
    finally:
        source_container.remove(force=True)


def _ensure_image(client, log):
    try:
        client.images.get(HELPER_IMAGE)
    except docker.errors.ImageNotFound:
        log(f"Образ {HELPER_IMAGE} не найден, загрузка...")
        client.images.pull(HELPER_IMAGE)

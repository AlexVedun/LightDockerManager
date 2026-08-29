import docker.errors
from PySide6.QtCore import QCoreApplication

HELPER_IMAGE = "alpine:latest"
MOUNT_PATH = "/data"


def transfer_volume(source_client, source_volume_name, dest_client, dest_volume_name, log=lambda msg: None):
    """Copy the contents of a volume from one Docker host to another.

    Both clients may point at the same daemon or at different ones (e.g. local
    and a remote SSH connection); the tar stream is piped directly between the
    two API calls without buffering the whole volume in memory.
    """
    log(
        QCoreApplication.translate("VolumeTransfer", "Checking helper image {image} on the source...")
        .format(image=HELPER_IMAGE)
    )
    _ensure_image(source_client, log)
    log(
        QCoreApplication.translate("VolumeTransfer", "Checking helper image {image} on the destination...")
        .format(image=HELPER_IMAGE)
    )
    _ensure_image(dest_client, log)

    log(
        QCoreApplication.translate("VolumeTransfer", 'Creating destination volume "{name}" (if missing)...')
        .format(name=dest_volume_name)
    )
    dest_client.volumes.create(name=dest_volume_name)

    log(QCoreApplication.translate("VolumeTransfer", "Creating helper container on the source..."))
    source_container = source_client.containers.create(
        HELPER_IMAGE,
        "true",
        volumes={source_volume_name: {"bind": MOUNT_PATH, "mode": "ro"}},
    )
    try:
        log(QCoreApplication.translate("VolumeTransfer", "Creating helper container on the destination..."))
        dest_container = dest_client.containers.create(
            HELPER_IMAGE,
            "true",
            volumes={dest_volume_name: {"bind": MOUNT_PATH, "mode": "rw"}},
        )
        try:
            log(
                QCoreApplication.translate("VolumeTransfer", 'Reading contents of volume "{name}"...')
                .format(name=source_volume_name)
            )
            stream, stat = source_container.get_archive(f"{MOUNT_PATH}/.")
            log(
                QCoreApplication.translate("VolumeTransfer", 'Writing contents to volume "{name}" (~{size} bytes)...')
                .format(name=dest_volume_name, size=stat.get("size", "?"))
            )
            dest_container.put_archive(MOUNT_PATH, stream)
            log(QCoreApplication.translate("VolumeTransfer", "Transfer completed successfully."))
        finally:
            dest_container.remove(force=True)
    finally:
        source_container.remove(force=True)


def _ensure_image(client, log):
    try:
        client.images.get(HELPER_IMAGE)
    except docker.errors.ImageNotFound:
        log(
            QCoreApplication.translate("VolumeTransfer", "Image {image} not found, pulling...")
            .format(image=HELPER_IMAGE)
        )
        client.images.pull(HELPER_IMAGE)

import time

import docker.errors
from PySide6.QtCore import QCoreApplication

HELPER_IMAGE = "alpine:latest"
MOUNT_PATH = "/data"
PROGRESS_MIN_INTERVAL_SECONDS = 0.1


def transfer_volume(
    source_client,
    source_volume_name,
    dest_client,
    dest_volume_name,
    log=lambda msg: None,
    progress=lambda transferred, total: None,
):
    """Copy the contents of a volume from one Docker host to another.

    Both clients may point at the same daemon or at different ones (e.g. local
    and a remote SSH connection); the tar stream is piped directly between the
    two API calls without buffering the whole volume in memory.

    `progress(transferred, total)` is called as bytes stream across; `total`
    is `du`'s on-disk size estimate for the volume (or None if it couldn't be
    measured), so it undercounts a little versus the actual tar stream (which
    adds header/padding overhead per file) but is otherwise a real number,
    not a guess.
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
        ["sleep", "3600"],
        volumes={source_volume_name: {"bind": MOUNT_PATH, "mode": "ro"}},
    )
    try:
        source_container.start()

        log(
            QCoreApplication.translate("VolumeTransfer", 'Measuring size of volume "{name}"...')
            .format(name=source_volume_name)
        )
        total_size = _measure_size(source_container)

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
            stream, _stat = source_container.get_archive(f"{MOUNT_PATH}/.")
            log(
                QCoreApplication.translate("VolumeTransfer", 'Writing contents to volume "{name}"...')
                .format(name=dest_volume_name)
            )
            counter = {"transferred": 0}
            progress(0, total_size)
            dest_container.put_archive(
                MOUNT_PATH, _tracked_chunks(stream, counter, lambda transferred: progress(transferred, total_size))
            )
            progress(counter["transferred"], total_size)
            log(
                QCoreApplication.translate("VolumeTransfer", "Transfer completed successfully ({size} bytes).")
                .format(size=counter["transferred"])
            )
        finally:
            dest_container.remove(force=True)
    finally:
        source_container.remove(force=True)


def _measure_size(container):
    """Returns the on-disk byte size of the volume mounted in `container`, or None if it can't be determined."""
    try:
        exit_code, output = container.exec_run(["du", "-sk", MOUNT_PATH])
        if exit_code != 0:
            return None
        return int(output.decode().split()[0]) * 1024
    except (docker.errors.APIError, ValueError, IndexError, UnicodeDecodeError, TypeError):
        return None


def _tracked_chunks(chunks, counter, progress):
    """Yields `chunks` unchanged, reporting `progress(transferred)` along the way.

    `counter` lets the caller read back the real final byte count once the
    generator is exhausted. Emitting on every chunk would flood the UI (a
    large volume can be millions of small chunks), so reports are throttled
    to at most a few per second.
    """
    last_emit = 0.0
    for chunk in chunks:
        counter["transferred"] += len(chunk)
        now = time.monotonic()
        if now - last_emit >= PROGRESS_MIN_INTERVAL_SECONDS:
            progress(counter["transferred"])
            last_emit = now
        yield chunk


def _ensure_image(client, log):
    try:
        client.images.get(HELPER_IMAGE)
    except docker.errors.ImageNotFound:
        log(
            QCoreApplication.translate("VolumeTransfer", "Image {image} not found, pulling...")
            .format(image=HELPER_IMAGE)
        )
        client.images.pull(HELPER_IMAGE)

import os
import tempfile
import time
from pathlib import Path

import docker.errors
from PySide6.QtCore import QCoreApplication

HELPER_IMAGE = "alpine:latest"
MOUNT_PATH = "/data"
PROGRESS_MIN_INTERVAL_SECONDS = 0.1
FILE_CHUNK_SIZE = 1024 * 1024


class VolumeAlreadyExistsError(RuntimeError):
    pass


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


def export_volume(
    client,
    volume_name,
    file_path,
    log=lambda msg: None,
    progress=lambda transferred, total: None,
):
    """Stream a volume into a tar file, replacing the target only after success."""
    target_path = Path(file_path)
    log(
        QCoreApplication.translate("VolumeTransfer", "Checking helper image {image} on the source...")
        .format(image=HELPER_IMAGE)
    )
    _ensure_image(client, log)

    log(QCoreApplication.translate("VolumeTransfer", "Creating helper container on the source..."))
    container = client.containers.create(
        HELPER_IMAGE,
        ["sleep", "3600"],
        volumes={volume_name: {"bind": MOUNT_PATH, "mode": "ro"}},
    )
    temp_path = None
    try:
        container.start()
        log(
            QCoreApplication.translate("VolumeTransfer", 'Measuring size of volume "{name}"...')
            .format(name=volume_name)
        )
        total_size = _measure_size(container)
        log(
            QCoreApplication.translate("VolumeTransfer", 'Reading contents of volume "{name}"...')
            .format(name=volume_name)
        )
        stream, _stat = container.get_archive(f"{MOUNT_PATH}/.")
        log(
            QCoreApplication.translate("VolumeTransfer", 'Writing archive to "{path}"...')
            .format(path=str(target_path))
        )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        counter = {"transferred": 0}
        progress(0, total_size)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".part",
            delete=False,
        ) as output:
            temp_path = Path(output.name)
            for chunk in _tracked_chunks(
                stream,
                counter,
                lambda transferred: progress(transferred, total_size),
            ):
                output.write(chunk)
        os.replace(temp_path, target_path)
        temp_path = None
        progress(counter["transferred"], total_size)
        log(
            QCoreApplication.translate("VolumeTransfer", "Export completed successfully ({size} bytes).")
            .format(size=counter["transferred"])
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        container.remove(force=True)


def import_volume(
    client,
    volume_name,
    file_path,
    overwrite=False,
    log=lambda msg: None,
    progress=lambda transferred, total: None,
):
    """Stream a tar file into a volume, optionally clearing an existing volume first."""
    archive_path = Path(file_path)
    total_size = archive_path.stat().st_size
    try:
        client.volumes.get(volume_name)
        volume_exists = True
    except docker.errors.NotFound:
        volume_exists = False

    if volume_exists and not overwrite:
        raise VolumeAlreadyExistsError(
            QCoreApplication.translate("VolumeTransfer", 'Volume "{name}" already exists.')
            .format(name=volume_name)
        )

    log(
        QCoreApplication.translate("VolumeTransfer", "Checking helper image {image} on the destination...")
        .format(image=HELPER_IMAGE)
    )
    _ensure_image(client, log)
    if not volume_exists:
        log(
            QCoreApplication.translate("VolumeTransfer", 'Creating destination volume "{name}"...')
            .format(name=volume_name)
        )
        client.volumes.create(name=volume_name)

    log(QCoreApplication.translate("VolumeTransfer", "Creating helper container on the destination..."))
    container = client.containers.create(
        HELPER_IMAGE,
        ["sleep", "3600"],
        volumes={volume_name: {"bind": MOUNT_PATH, "mode": "rw"}},
    )
    try:
        container.start()
        if volume_exists:
            log(
                QCoreApplication.translate("VolumeTransfer", 'Clearing existing volume "{name}"...')
                .format(name=volume_name)
            )
            exit_code, output = container.exec_run(["sh", "-c", f"find {MOUNT_PATH} -mindepth 1 -delete"])
            if exit_code != 0:
                details = output.decode(errors="replace").strip()
                raise RuntimeError(
                    QCoreApplication.translate("VolumeTransfer", 'Could not clear volume "{name}": {error}')
                    .format(name=volume_name, error=details)
                )

        counter = {"transferred": 0}
        progress(0, total_size)
        log(
            QCoreApplication.translate("VolumeTransfer", 'Reading archive from "{path}"...')
            .format(path=str(archive_path))
        )
        log(
            QCoreApplication.translate("VolumeTransfer", 'Writing contents to volume "{name}"...')
            .format(name=volume_name)
        )
        with archive_path.open("rb") as archive:
            chunks = _file_chunks(archive)
            container.put_archive(
                MOUNT_PATH,
                _tracked_chunks(chunks, counter, lambda transferred: progress(transferred, total_size)),
            )
        progress(counter["transferred"], total_size)
        log(
            QCoreApplication.translate("VolumeTransfer", "Import completed successfully ({size} bytes).")
            .format(size=counter["transferred"])
        )
    finally:
        container.remove(force=True)


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


def _file_chunks(file_object):
    while True:
        chunk = file_object.read(FILE_CHUNK_SIZE)
        if not chunk:
            return
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

from types import SimpleNamespace

from PySide6.QtWidgets import QInputDialog, QMessageBox

from ui.volume_transfer_window import TransferWorker, _volume_name_from_archive
from ui.volume_transfer_window import VolumeTransferWindow


def test_progress_signal_preserves_byte_counts_larger_than_32_bit_int():
    worker = TransferWorker(None, "src-vol", None, "dst-vol")
    events = []
    transferred = 3 * 1024**3
    total = 80 * 1024**3

    worker.progress.connect(lambda current, expected: events.append((current, expected)))
    worker.progress.emit(transferred, total)

    assert events == [(transferred, total)]


def test_volume_name_is_derived_from_tar_file_name():
    assert _volume_name_from_archive("/backups/aur_core_mysql_data.tar") == "aur_core_mysql_data"
    assert _volume_name_from_archive("/backups/data.backup.TAR") == "data.backup"


def test_import_existing_volume_can_be_overwritten(monkeypatch):
    window = SimpleNamespace(
        dest_picker=SimpleNamespace(volume_names=lambda: {"existing"}),
        tr=lambda text: text,
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    assert VolumeTransferWindow._resolve_import_destination(window, "existing") == ("existing", True)


def test_import_existing_volume_asks_for_new_name_when_overwrite_is_declined(monkeypatch):
    window = SimpleNamespace(
        dest_picker=SimpleNamespace(volume_names=lambda: {"existing"}),
        tr=lambda text: text,
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("restored", True))

    assert VolumeTransferWindow._resolve_import_destination(window, "existing") == ("restored", False)


def test_import_reprompts_when_new_volume_name_is_empty(monkeypatch):
    window = SimpleNamespace(
        dest_picker=SimpleNamespace(volume_names=lambda: {"existing"}),
        tr=lambda text: text,
    )
    answers = iter([("  ", True), ("restored", True)])
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.No)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args[2]))
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: next(answers))

    assert VolumeTransferWindow._resolve_import_destination(window, "existing") == ("restored", False)
    assert warnings == ["Volume name cannot be empty."]

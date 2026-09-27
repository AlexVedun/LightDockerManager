from ui.volume_transfer_window import TransferWorker


def test_progress_signal_preserves_byte_counts_larger_than_32_bit_int():
    worker = TransferWorker(None, "src-vol", None, "dst-vol")
    events = []
    transferred = 3 * 1024**3
    total = 80 * 1024**3

    worker.progress.connect(lambda current, expected: events.append((current, expected)))
    worker.progress.emit(transferred, total)

    assert events == [(transferred, total)]

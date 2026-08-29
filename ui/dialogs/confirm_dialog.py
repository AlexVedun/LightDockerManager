from PySide6.QtWidgets import QMessageBox


def confirm(parent, title, text):
    answer = QMessageBox.question(
        parent,
        title,
        text,
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    return answer == QMessageBox.Yes

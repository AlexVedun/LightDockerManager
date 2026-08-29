import json

from PySide6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout


class InspectDialog(QDialog):
    def __init__(self, title, attrs, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(700, 600)

        text_edit = QPlainTextEdit(self)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(json.dumps(attrs, indent=2, default=str))

        layout = QVBoxLayout(self)
        layout.addWidget(text_edit)

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from connection.profiles import load_profiles, save_profiles


class ProfileEditDialog(QDialog):
    def __init__(self, profile=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Подключение по SSH")

        self.name_edit = QLineEdit(profile["name"] if profile else "")
        self.host_edit = QLineEdit(profile["host"] if profile else "")
        self.user_edit = QLineEdit(profile["user"] if profile else "")
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(profile.get("port", 22) if profile else 22)

        form = QFormLayout()
        form.addRow("Название:", self.name_edit)
        form.addRow("Хост:", self.host_edit)
        form.addRow("Пользователь:", self.user_edit)
        form.addRow("Порт:", self.port_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self):
        if not self.name_edit.text().strip() or not self.host_edit.text().strip() or not self.user_edit.text().strip():
            QMessageBox.warning(self, "Проверка данных", "Заполните название, хост и пользователя.")
            return
        self.accept()

    def get_profile(self):
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "user": self.user_edit.text().strip(),
            "port": self.port_spin.value(),
        }


class ManageConnectionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление подключениями")
        self.resize(400, 300)
        self.profiles = load_profiles()

        self.list_widget = QListWidget(self)
        self._reload_list()

        self.btn_add = QPushButton("Добавить")
        self.btn_edit = QPushButton("Изменить")
        self.btn_remove = QPushButton("Удалить")

        self.btn_add.clicked.connect(self._add_profile)
        self.btn_edit.clicked.connect(self._edit_profile)
        self.btn_remove.clicked.connect(self._remove_profile)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(self.btn_add)
        buttons_row.addWidget(self.btn_edit)
        buttons_row.addWidget(self.btn_remove)

        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        close_box.accepted.connect(self.accept)
        close_box.button(QDialogButtonBox.Close).clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addLayout(buttons_row)
        layout.addWidget(close_box)

    def _reload_list(self):
        self.list_widget.clear()
        for profile in self.profiles:
            item = QListWidgetItem(f"{profile['name']} ({profile['user']}@{profile['host']}:{profile.get('port', 22)})")
            self.list_widget.addItem(item)

    def _add_profile(self):
        dialog = ProfileEditDialog(parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.profiles.append(dialog.get_profile())
            save_profiles(self.profiles)
            self._reload_list()

    def _edit_profile(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        dialog = ProfileEditDialog(profile=self.profiles[row], parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.profiles[row] = dialog.get_profile()
            save_profiles(self.profiles)
            self._reload_list()

    def _remove_profile(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        profile = self.profiles[row]
        answer = QMessageBox.question(
            self, "Удалить подключение", f"Удалить подключение \"{profile['name']}\"?"
        )
        if answer != QMessageBox.Yes:
            return
        del self.profiles[row]
        save_profiles(self.profiles)
        self._reload_list()

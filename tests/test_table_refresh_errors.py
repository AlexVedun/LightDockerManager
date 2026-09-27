from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from ui.tables.containers_table import ContainersTab
from ui.tables.images_table import ImagesTab
from ui.tables.networks_table import NetworksTab
from ui.tables.volumes_table import VolumesTab

QApplication.instance() or QApplication([])


@pytest.mark.parametrize("tab_type", [ContainersTab, ImagesTab, NetworksTab, VolumesTab])
def test_background_refresh_error_is_reported_without_modal_dialog(tab_type):
    messages = []
    tab = tab_type(SimpleNamespace(client=None), notify=messages.append)
    tab._refreshing = True

    tab._on_refresh_failed("read timed out")

    assert tab._refreshing is False
    assert messages == ["read timed out"]

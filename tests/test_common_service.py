from unittest.mock import MagicMock

from docker_services.common import reload_and_get_attrs


def test_reload_and_get_attrs_reloads_then_returns_attrs():
    obj = MagicMock()
    obj.attrs = {"Id": "abc123"}

    result = reload_and_get_attrs(obj)

    obj.reload.assert_called_once()
    assert result == {"Id": "abc123"}

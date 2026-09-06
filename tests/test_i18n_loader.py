from unittest.mock import MagicMock

import i18n_loader


def test_resolve_language_returns_explicit_supported_language():
    assert i18n_loader.resolve_language({"language": "ru"}) == "ru"
    assert i18n_loader.resolve_language({"language": "uk"}) == "uk"
    assert i18n_loader.resolve_language({"language": "en"}) == "en"


def test_resolve_language_falls_back_to_system_locale(monkeypatch):
    monkeypatch.setattr(i18n_loader, "QLocale", MagicMock())
    i18n_loader.QLocale.system.return_value.name.return_value = "ru_RU"

    assert i18n_loader.resolve_language({"language": "auto"}) == "ru"


def test_resolve_language_falls_back_to_english_for_unsupported_locale(monkeypatch):
    monkeypatch.setattr(i18n_loader, "QLocale", MagicMock())
    i18n_loader.QLocale.system.return_value.name.return_value = "fr_FR"

    assert i18n_loader.resolve_language({"language": "auto"}) == "en"


def _stub_translators(monkeypatch, *, qtbase_loads, qm_loads):
    """Makes each `QTranslator()` construction return a fresh mock, in order:
    the Qt base translator first, then (if attempted) the app's own."""
    created = []
    load_results = iter([qtbase_loads, qm_loads])

    def make_translator():
        translator = MagicMock()
        translator.load.return_value = next(load_results, False)
        created.append(translator)
        return translator

    monkeypatch.setattr(i18n_loader, "QTranslator", make_translator)
    monkeypatch.setattr(i18n_loader, "QLibraryInfo", MagicMock())
    return created


def test_install_translator_skips_english():
    assert i18n_loader.install_translator(MagicMock(), "en") is None


def test_install_translator_returns_none_when_nothing_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)
    _stub_translators(monkeypatch, qtbase_loads=False, qm_loads=False)

    assert i18n_loader.install_translator(MagicMock(), "ru") is None


def test_install_translator_loads_and_installs_qm(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)
    (tmp_path / "lightdockermanager_ru.qm").write_bytes(b"fake")
    created = _stub_translators(monkeypatch, qtbase_loads=False, qm_loads=True)

    app = MagicMock()
    result = i18n_loader.install_translator(app, "ru")

    assert result == [created[1]]
    app.installTranslator.assert_called_once_with(created[1])
    created[1].load.assert_called_once_with(str(tmp_path / "lightdockermanager_ru.qm"))


def test_install_translator_loads_qt_base_translation_for_standard_widgets(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)
    created = _stub_translators(monkeypatch, qtbase_loads=True, qm_loads=False)

    app = MagicMock()
    result = i18n_loader.install_translator(app, "ru")

    assert result == [created[0]]
    app.installTranslator.assert_called_once_with(created[0])
    created[0].load.assert_called_once_with("qtbase_ru", i18n_loader.QLibraryInfo.path.return_value)


def test_install_translator_installs_both_when_both_load(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)
    (tmp_path / "lightdockermanager_ru.qm").write_bytes(b"fake")
    created = _stub_translators(monkeypatch, qtbase_loads=True, qm_loads=True)

    app = MagicMock()
    result = i18n_loader.install_translator(app, "ru")

    assert result == created
    assert app.installTranslator.call_count == 2

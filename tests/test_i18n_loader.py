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


def test_install_translator_skips_english():
    assert i18n_loader.install_translator(MagicMock(), "en") is None


def test_install_translator_returns_none_when_qm_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)

    assert i18n_loader.install_translator(MagicMock(), "ru") is None


def test_install_translator_loads_and_installs_qm(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n_loader, "I18N_DIR", tmp_path)
    (tmp_path / "lightdockermanager_ru.qm").write_bytes(b"fake")

    fake_translator = MagicMock()
    fake_translator.load.return_value = True
    monkeypatch.setattr(i18n_loader, "QTranslator", lambda: fake_translator)

    app = MagicMock()
    result = i18n_loader.install_translator(app, "ru")

    assert result is fake_translator
    app.installTranslator.assert_called_once_with(fake_translator)

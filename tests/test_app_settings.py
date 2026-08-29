import app_settings


def test_load_settings_returns_defaults_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")

    assert app_settings.load_settings() == {"language": "auto"}


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(app_settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(app_settings, "CONFIG_FILE", tmp_path / "settings.json")

    app_settings.save_settings({"language": "ru"})

    assert app_settings.load_settings() == {"language": "ru"}


def test_load_settings_returns_defaults_on_corrupt_file(tmp_path, monkeypatch):
    config_file = tmp_path / "settings.json"
    config_file.write_text("not valid json")
    monkeypatch.setattr(app_settings, "CONFIG_FILE", config_file)

    assert app_settings.load_settings() == {"language": "auto"}

from connection import profiles


def test_load_profiles_returns_empty_list_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "CONFIG_FILE", tmp_path / "connections.json")

    assert profiles.load_profiles() == []


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(profiles, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(profiles, "CONFIG_FILE", tmp_path / "connections.json")

    data = [{"name": "Laptop", "host": "192.168.1.50", "user": "alex", "port": 22}]
    profiles.save_profiles(data)

    assert profiles.load_profiles() == data


def test_load_profiles_returns_empty_list_on_corrupt_file(tmp_path, monkeypatch):
    config_file = tmp_path / "connections.json"
    config_file.write_text("not valid json")
    monkeypatch.setattr(profiles, "CONFIG_FILE", config_file)

    assert profiles.load_profiles() == []

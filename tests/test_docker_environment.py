import os

from connection import docker_environment


def _fake_helper(directory):
    directory.mkdir(parents=True)
    helper = directory / docker_environment.DOCKER_CREDENTIAL_HELPER
    helper.write_text("helper")
    helper.chmod(0o755)


def test_adds_user_docker_bin_to_gui_path_on_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_environment.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(docker_environment, "DOCKER_DESKTOP_BIN", tmp_path / "absent")
    docker_bin = tmp_path / ".docker" / "bin"
    _fake_helper(docker_bin)

    docker_environment.configure_docker_desktop_path()
    docker_environment.configure_docker_desktop_path()

    assert os.environ["PATH"].split(os.pathsep) == ["/usr/bin", "/bin", str(docker_bin)]


def test_uses_docker_app_bin_when_user_symlink_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_environment.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    docker_app_bin = tmp_path / "Docker.app" / "Contents" / "Resources" / "bin"
    monkeypatch.setattr(docker_environment, "DOCKER_DESKTOP_BIN", docker_app_bin)
    _fake_helper(docker_app_bin)

    docker_environment.configure_docker_desktop_path()

    assert os.environ["PATH"].split(os.pathsep) == ["/usr/bin", "/bin", str(docker_app_bin)]


def test_other_platforms_leave_path_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(docker_environment.sys, "platform", "linux")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    _fake_helper(tmp_path / ".docker" / "bin")

    docker_environment.configure_docker_desktop_path()

    assert os.environ["PATH"] == "/usr/bin:/bin"

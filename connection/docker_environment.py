import os
import sys
from pathlib import Path

DOCKER_DESKTOP_BIN = Path("/Applications/Docker.app/Contents/Resources/bin")
DOCKER_CREDENTIAL_HELPER = "docker-credential-desktop"


def configure_docker_desktop_path():
    """Make Docker Desktop's credential helper visible to macOS GUI launches."""
    if sys.platform != "darwin":
        return

    path_entries = [entry for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]
    for directory in (Path.home() / ".docker" / "bin", DOCKER_DESKTOP_BIN):
        helper = directory / DOCKER_CREDENTIAL_HELPER
        if helper.is_file() and os.access(helper, os.X_OK) and str(directory) not in path_entries:
            path_entries.append(str(directory))
    os.environ["PATH"] = os.pathsep.join(path_entries)

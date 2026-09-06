# LightDockerManager

A lightweight desktop GUI for managing Docker — containers, images, volumes and networks — built with Python and PySide6 (Qt). "Light" refers to the app itself: no daemon, no Electron, no web stack, just a small native client that talks to the Docker Engine API through `docker-py`.

## Features

- **Containers, Images, Volumes, Networks** tabs — list, filter-free tables with bulk actions (start/stop/restart/pause/unpause/remove) via row checkboxes.
- **Compose-project grouping** — containers are automatically clustered by their `com.docker.compose.project` label, with a group header row and a "select whole group" checkbox, so starting/stopping an entire project is one click.
- **Local and remote (SSH) connections** — switch between the local Docker daemon and any number of saved SSH-based remote hosts.
- **Volume transfer** — copy a volume's contents directly between two hosts (local↔remote or remote↔remote) by streaming a tar archive between them, no intermediate files.
- **Live updates** — a background Docker events listener refreshes the relevant tab as soon as something changes.
- **Logs viewer and inspect dialogs** for containers.
- **Localization** — English, Russian and Ukrainian, auto-detected from the system locale or selectable in the app.
- **Persisted UI state** — column widths and sort order are remembered per table across restarts.

## Tech stack

- Python 3, [PySide6](https://doc.qt.io/qtforpython/) (Qt) for the UI
- [docker-py](https://docker-py.readthedocs.io/) for talking to the Docker Engine API (local socket or SSH)
- [paramiko](https://www.paramiko.org/) for SSH-based remote connections
- PyInstaller for packaging (Linux AppImage, and Windows/macOS builds via the `.spec` file)

## Getting started

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Requires a running Docker daemon (local socket, or SSH access to a remote host with Docker installed).

## Running tests

```bash
pip install -r requirements.txt -r requirements-build.txt
pytest
```

## Packaging

A Linux AppImage can be built with:

```bash
packaging/build_appimage.sh
```

Windows/macOS builds use the PyInstaller spec file:

```bash
pyinstaller LightDockerManager.spec
```

## License

No license file is currently included; all rights reserved by the author unless stated otherwise.

# LightDockerManager

A lightweight desktop GUI for managing Docker — containers, images, volumes and networks — built with Python and PySide6 (Qt). "Light" refers to the app itself: no daemon, no Electron, no web stack, just a small native client that talks to the Docker Engine API through `docker-py`.

*Легкий десктопний GUI для керування Docker — контейнерами, образами, томами та мережами — на Python і PySide6 (Qt). "Light" стосується самого застосунку: жодного демона, Electron чи веб-стеку — лише невеликий нативний клієнт, що спілкується з Docker Engine API через `docker-py`.*

## Features / Можливості

- **Containers, Images, Volumes, Networks** tabs — list, filter-free tables with bulk actions (start/stop/restart/pause/unpause/remove) via row checkboxes.
  *Вкладки Containers, Images, Volumes, Networks — таблиці з масовими діями (запуск/зупинка/перезапуск/пауза/зняття з паузи/видалення) через чекбокси рядків.*
- **Compose-project grouping** — containers are automatically clustered by their `com.docker.compose.project` label, with a group header row and a "select whole group" checkbox, so starting/stopping an entire project is one click.
  *Групування за Compose-проєктами — контейнери автоматично групуються за лейблом `com.docker.compose.project`, із заголовком групи та чекбоксом «вибрати всю групу» для запуску/зупинки одним кліком.*
- **Local and remote (SSH) connections** — switch between the local Docker daemon and any number of saved SSH-based remote hosts.
  *Локальні та віддалені (SSH) з'єднання — перемикання між локальним Docker-демоном і будь-якою кількістю збережених віддалених хостів через SSH.*
- **Volume transfer** — copy a volume's contents directly between two hosts (local↔remote or remote↔remote) by streaming a tar archive between them, no intermediate files.
  *Перенесення томів — копіювання вмісту тому напряму між двома хостами (локальний↔віддалений або віддалений↔віддалений) потоковою передачею tar-архіву без проміжних файлів.*
- **Live updates** — a background Docker events listener refreshes the relevant tab as soon as something changes.
  *Живі оновлення — фоновий слухач подій Docker оновлює відповідну вкладку одразу після будь-якої зміни.*
- **Logs viewer and inspect dialogs** for containers.
  *Перегляд логів та inspect-діалоги для контейнерів.*
- **Localization** — English, Russian and Ukrainian, auto-detected from the system locale or selectable in the app.
  *Локалізація — англійська, російська та українська, з автовизначенням за системною локаллю або ручним вибором.*
- **Persisted UI state** — column widths and sort order are remembered per table across restarts.
  *Збереження стану інтерфейсу — ширина колонок і порядок сортування запам'ятовуються для кожної таблиці між запусками.*

## Tech stack / Технологічний стек

- Python 3, [PySide6](https://doc.qt.io/qtforpython/) (Qt) for the UI
- [docker-py](https://docker-py.readthedocs.io/) for talking to the Docker Engine API (local socket or SSH)
- [paramiko](https://www.paramiko.org/) for SSH-based remote connections
- PyInstaller for packaging (Linux AppImage, and Windows/macOS builds via the `.spec` file)

## Getting started / Початок роботи

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Requires a running Docker daemon (local socket, or SSH access to a remote host with Docker installed).

*Потребує запущеного Docker-демона (локальний сокет або SSH-доступ до віддаленого хоста з установленим Docker).*

## Running tests / Запуск тестів

```bash
pip install -r requirements.txt -r requirements-build.txt
pytest
```

## Packaging / Пакування

A Linux AppImage can be built with:

*Linux AppImage можна зібрати командою:*

```bash
packaging/build_appimage.sh
```

Windows/macOS builds use the PyInstaller spec file:

*Для Windows/macOS збірки використовується spec-файл PyInstaller:*

```bash
pyinstaller LightDockerManager.spec
```

## License / Ліцензія

No license file is currently included; all rights reserved by the author unless stated otherwise.

*Файл ліцензії наразі відсутній; усі права належать автору, якщо не вказано інше.*

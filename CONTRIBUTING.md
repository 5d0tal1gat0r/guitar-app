# Contributing

Guitar Practice is an early Linux desktop application. Focus contributions on reliable
practice feedback, useful exercises and predictable audio behavior.

## Set up

Install Python 3.12+, `uv` and PortAudio, then run:

```sh
uv sync --extra dev
uv run pytest
QT_QPA_PLATFORM=offscreen uv run python -c \
  "from PySide6.QtWidgets import QApplication; from guitarapp.ui import MainWindow; app = QApplication([]); MainWindow().close()"
```

## Changes

- Open an issue before a large UI, audio or file-format change.
- Keep pitch detection, practice scoring and file parsing independent from Qt where possible.
- Add focused tests for behavior changes. Use generated or original fixtures; do not commit
  copyrighted songs or commercial tab files.
- Run the full test suite before opening a pull request.
- Use a short-lived branch and a descriptive commit message.

When reporting audio problems, include the Linux distribution, audio server, input device,
sample rate and a precise description of what you heard or saw. Do not attach recordings you
do not have permission to share.

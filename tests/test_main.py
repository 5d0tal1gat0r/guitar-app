import subprocess
import sys

import guitarapp
import pytest

from guitarapp.__main__ import main


def test_version_flag_prints_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"guitar-app {guitarapp.__version__}\n"


def test_module_version_flag_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "guitarapp", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert guitarapp.__version__ in result.stdout


def test_version_flag_does_not_import_ui():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from guitarapp.__main__ import main\n"
            "try: main(['--version'])\n"
            "except SystemExit: pass\n"
            "print('guitarapp.ui' in sys.modules)",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.endswith("False\n")

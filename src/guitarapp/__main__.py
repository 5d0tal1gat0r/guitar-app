"""Entry point: `guitar-app` or `python -m guitarapp`."""

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="guitar-app",
        description="Guitar practice app for Linux.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)

    from .ui import run

    return run()


if __name__ == "__main__":
    sys.exit(main())

"""Entry point: `guitar-app` or `python -m guitarapp`."""

import sys


def main() -> int:
    from .ui import run

    return run()


if __name__ == "__main__":
    sys.exit(main())

"""Package entry point for ``python -m silta``.

This forwards to the CLI's main function so you can run:

    python -m silta gui

or

    python -m silta server
"""

from .cli import main as _cli_main


def main() -> None:  # pragma: no cover - thin wrapper
    _cli_main()


if __name__ == "__main__":  # pragma: no cover
    main()

# SPDX-License-Identifier: GPL-3.0-or-later
"""Entry point: `ichnos` / `python -m ichnos`.

`ichnos show ...`, `ichnos strip ...` and options like --help go to the
command-line interface. Anything else is treated as files to open in the app.
Qt is only imported when the app actually starts, so the command line works
on machines without a display.
"""

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv

    from ichnos.cli import COMMANDS

    if args and (args[0] in COMMANDS or (args[0].startswith("-") and args[0] != "--")):
        from ichnos.cli import main as cli_main

        return cli_main(args)

    if args[:1] == ["--"]:  # `ichnos -- strip` opens a file named "strip"
        args = args[1:]

    from ichnos.gui.app import run

    return run(args)


if __name__ == "__main__":
    sys.exit(main())

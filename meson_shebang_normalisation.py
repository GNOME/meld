#!/usr/bin/env python3

import pathlib
import sys


def main():
    from argparse import ArgumentParser

    parser = ArgumentParser(description="normalize shebang line, for meson")
    parser.add_argument("--wheel", action="store_true")
    parser.add_argument("in_path", type=pathlib.Path)
    parser.add_argument("out_path", type=pathlib.Path)
    args = parser.parse_args()
    in_path, out_path, wheel = args.in_path, args.out_path, args.wheel

    if not in_path.exists():
        print(f"Couldn't find {in_path}")
        sys.exit(1)

    lines = in_path.read_text().splitlines(keepends=True)
    if wheel:
        lines[0] = "#!python"
    else:
        lines[0] = "".join(lines[0].split("env "))
    out_path.write_text("".join(lines))

    stat = in_path.stat()
    out_path.chmod(stat.st_mode)


if __name__ == "__main__":
    main()

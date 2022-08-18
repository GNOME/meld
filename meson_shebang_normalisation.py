#!/usr/bin/env python3

import pathlib
import sys


def main():
    in_path = pathlib.Path(sys.argv[1])
    out_path = pathlib.Path(sys.argv[2])
    if not in_path.exists():
        print(f"Couldn't find {in_path}")
        sys.exit(1)

    lines = in_path.read_text().splitlines(keepends=True)
    lines[0] = "".join(lines[0].split("env "))
    out_path.write_text("".join(lines))

    stat = in_path.stat()
    out_path.chmod(stat.st_mode)


if __name__ == "__main__":
    main()

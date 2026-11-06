"""Fail fast when the project is not using its pinned Windows runtime."""
from __future__ import annotations

import platform
import struct
import sys

EXPECTED = (3, 13, 15)


def runtime_errors() -> list[str]:
    errors: list[str] = []
    if platform.python_implementation() != "CPython":
        errors.append("CPython is required.")
    if sys.version_info[:3] != EXPECTED:
        errors.append(f"Python {'.'.join(map(str, EXPECTED))} is required.")
    if struct.calcsize("P") * 8 != 64:
        errors.append("A 64-bit Python interpreter is required.")
    return errors


def main() -> int:
    bits = struct.calcsize("P") * 8
    print(f"Implementation: {platform.python_implementation()}")
    print(f"Version: {platform.python_version()}")
    print(f"Architecture: {bits}-bit")
    print(f"Executable: {sys.executable}")
    errors = runtime_errors()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

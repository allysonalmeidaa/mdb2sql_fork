#!/usr/bin/env python3
import importlib
import platform
import sys


def check_module(name):
    try:
        importlib.import_module(name)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def main():
    bits = 64 if sys.maxsize > 2**32 else 32
    print("python_version:", sys.version.split()[0])
    print("python_bits:", bits)
    print("platform:", platform.platform())

    modules = ["duckdb", "pyodbc", "pypyodbc", "access_parser"]
    optional = ["access_parser_access"]
    for mod in modules:
        ok, err = check_module(mod)
        print(f"module:{mod}:", "ok" if ok else f"missing ({err})")
    for mod in optional:
        ok, err = check_module(mod)
        print(f"module:{mod}:", "ok" if ok else f"optional missing ({err})")

    try:
        import pyodbc  # type: ignore
        drivers = pyodbc.drivers()
        print("odbc_drivers:", ", ".join(drivers))
        has_access = any("Access Driver" in d for d in drivers)
        print("access_odbc_driver:", "ok" if has_access else "missing")
    except Exception as exc:
        print("odbc_drivers: error", str(exc))


if __name__ == "__main__":
    main()

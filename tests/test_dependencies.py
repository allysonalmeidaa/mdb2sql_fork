import json
from pathlib import Path


def test_python_requirements_contains_expected():
    reqs = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    reqs = {line.strip() for line in reqs if line.strip() and not line.startswith("#")}
    expected = {
        "duckdb",
        "flask",
        "rapidfuzz",
        "pyodbc",
        "pypyodbc",
        "pandas",
        "access-parser",
    }
    missing = expected - reqs
    assert not missing, f"missing requirements: {missing}"


def test_node_dependencies_contains_playwright():
    pkg = json.loads(Path("package.json").read_text(encoding="utf-8"))
    dev = pkg.get("devDependencies") or {}
    assert "@playwright/test" in dev

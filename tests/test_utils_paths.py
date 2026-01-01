import os
import tempfile
import unittest
from pathlib import Path

from interface.utils import clamp_int, resolve_db_path


class TestUtilsPaths(unittest.TestCase):
    def test_resolve_db_path_explicit(self):
        path = Path("some/where.db")
        self.assertEqual(resolve_db_path(path), path)

    def test_resolve_db_path_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "file.duckdb"
            db.touch()
            old = os.environ.get("DB_PATH")
            os.environ["DB_PATH"] = str(db)
            try:
                self.assertEqual(resolve_db_path(), db)
            finally:
                if old is None:
                    os.environ.pop("DB_PATH", None)
                else:
                    os.environ["DB_PATH"] = old

    def test_resolve_db_path_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(resolve_db_path(uploads_dir=Path(tmp)))

    def test_resolve_db_path_multiple(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.duckdb").touch()
            Path(tmp, "b.duckdb").touch()
            old = os.environ.get("DB_PATH")
            os.environ.pop("DB_PATH", None)
            try:
                with self.assertRaises(ValueError):
                    resolve_db_path(uploads_dir=Path(tmp))
            finally:
                if old is None:
                    os.environ.pop("DB_PATH", None)
                else:
                    os.environ["DB_PATH"] = old

    def test_clamp_int(self):
        self.assertEqual(clamp_int("5", 1, min_value=0, max_value=10), 5)
        self.assertEqual(clamp_int("bad", 7), 7)
        self.assertEqual(clamp_int(-2, 0, min_value=0), 0)
        self.assertEqual(clamp_int(50, 0, max_value=10), 10)

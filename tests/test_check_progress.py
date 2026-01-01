import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import duckdb

from interface import check_progress


class TestCheckProgress(unittest.TestCase):
    def test_check_progress_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "sample.duckdb"
            conn = duckdb.connect(str(db_path))
            conn.execute("CREATE TABLE t (id INTEGER)")
            conn.execute("INSERT INTO t VALUES (1)")
            conn.close()
            output = io.StringIO()
            argv = ["check_progress.py", "--db", str(db_path)]
            with mock.patch.object(sys, "argv", argv):
                with redirect_stdout(output):
                    check_progress.main()
            self.assertIn("Found", output.getvalue())

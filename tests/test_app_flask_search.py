import os
import tempfile
import unittest
from pathlib import Path

import duckdb

from interface import app_flask_search


class TestAppFlaskSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.duckdb"
        conn = duckdb.connect(str(self.db_path))
        conn.execute("CREATE TABLE t (id INTEGER, name VARCHAR)")
        conn.execute("INSERT INTO t VALUES (1, 'alpha'), (2, 'beta')")
        conn.close()
        self.old_env = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = str(self.db_path)
        app_flask_search.app.config["TESTING"] = True
        self.client = app_flask_search.app.test_client()

    def tearDown(self):
        if self.old_env is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self.old_env
        self.tmp.cleanup()

    def test_api_tables(self):
        res = self.client.get("/api/tables")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("tables", data)
        self.assertIn("t", data["tables"])

    def test_api_table_ok(self):
        res = self.client.get("/api/table?name=t&limit=1&offset=0")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("columns", data)
        self.assertIn("rows", data)
        self.assertIn("id", data["columns"])
        self.assertIn("name", data["columns"])
        self.assertEqual(len(data["rows"]), 1)

    def test_api_table_missing(self):
        res = self.client.get("/api/table?name=missing")
        self.assertEqual(res.status_code, 404)

    def test_api_search(self):
        res = self.client.get("/api/search?q=alpha")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("results", data)
        self.assertIn("t", data["results"])
        rows = data["results"]["t"]["rows"]
        self.assertTrue(any("alpha" in row for row in rows))

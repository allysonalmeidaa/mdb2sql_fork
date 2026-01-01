import tempfile
import unittest
from pathlib import Path

import duckdb
import interface.app_flask_local_search as app_module


class AdminStartIndexTests(unittest.TestCase):
    def _join_index_thread(self):
        thread = app_module.index_thread
        if thread and thread.is_alive():
            thread.join(timeout=2)

    def setUp(self):
        self.client = app_module.app.test_client()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self._orig_create = app_module.create_or_resume_fulltext
        app_module.create_or_resume_fulltext = lambda *args, **kwargs: None
        app_module.index_thread = None
        app_module._runtime_db_path = None

    def tearDown(self):
        self._join_index_thread()
        app_module.create_or_resume_fulltext = self._orig_create
        app_module.index_thread = None
        app_module._runtime_db_path = None
        self.temp_dir.cleanup()

    def test_start_index_requires_db(self):
        resp = self.client.post("/admin/start_index", json={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn("error", data)

    def test_start_index_requires_duckdb(self):
        accdb = self.temp_path / "test.accdb"
        accdb.write_text("", encoding="utf-8")
        app_module._runtime_db_path = str(accdb)
        resp = self.client.post("/admin/start_index", json={})
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertIn("error", data)

    def test_start_index_accepts_duckdb(self):
        duckdb_file = self.temp_path / "test.duckdb"
        conn = duckdb.connect(str(duckdb_file))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.close()
        app_module._runtime_db_path = str(duckdb_file)
        resp = self.client.post(
            "/admin/start_index", json={"drop": False, "chunk": 10, "batch": 10}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("ok"))

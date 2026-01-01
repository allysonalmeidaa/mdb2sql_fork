import gzip
import json
import unittest

import interface.app_flask_local_search as app_module


class AdminListUploadsTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.upload_dir = app_module.UPLOAD_DIR
        self.test_file = self.upload_dir / "__test_admin_list_uploads__.tmp"
        self.created = False
        if not self.test_file.exists():
            self.test_file.write_text("test", encoding="utf-8")
            self.created = True

    def tearDown(self):
        if self.created and self.test_file.exists():
            self.test_file.unlink()

    def test_admin_list_uploads_has_metadata(self):
        resp = self.client.get("/admin/list_uploads")
        self.assertEqual(resp.status_code, 200)
        data_bytes = resp.data
        if resp.headers.get("Content-Encoding") == "gzip":
            data_bytes = gzip.decompress(data_bytes)
        data = json.loads(data_bytes.decode("utf-8"))
        self.assertIsInstance(data, dict)
        uploads = data.get("uploads", [])
        self.assertIsInstance(uploads, list)
        match = next((f for f in uploads if f.get("name") == self.test_file.name), None)
        self.assertIsNotNone(match)
        self.assertIn("size", match)
        self.assertIn("modified", match)
        self.assertIn("ext", match)
        self.assertEqual(match.get("size"), self.test_file.stat().st_size)

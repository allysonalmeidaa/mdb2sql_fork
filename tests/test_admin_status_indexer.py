import unittest

import interface.app_flask_local_search as app_module


class AdminStatusIndexerTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.orig_indexer = app_module.create_or_resume_fulltext
        self.orig_indexer_error = app_module.create_fulltext_error

    def tearDown(self):
        app_module.create_or_resume_fulltext = self.orig_indexer
        app_module.create_fulltext_error = self.orig_indexer_error

    def test_admin_status_reports_indexer_missing(self):
        app_module.create_or_resume_fulltext = None
        app_module.create_fulltext_error = "create_fulltext missing"
        resp = self.client.get("/admin/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIsInstance(data, dict)
        self.assertFalse(data.get("indexer_available", True))
        self.assertEqual(data.get("indexer_error"), "create_fulltext missing")

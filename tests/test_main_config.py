import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import main as main_module


class MainConfigTests(unittest.TestCase):
    def test_resolve_upload_folder_default(self):
        base_dir = Path(main_module.__file__).resolve().parent
        resolved = main_module.resolve_upload_folder(None, base_dir)
        self.assertEqual(resolved.name, "uploads")
        self.assertEqual(resolved.parent.name, "interface")

    def test_resolve_upload_folder_custom(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            custom = Path(temp_dir) / "custom_uploads"
            resolved = main_module.resolve_upload_folder(str(custom), Path(temp_dir))
            self.assertEqual(resolved, custom.resolve())

    def test_validar_configuracao_invalid_port(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir) / "uploads"
            args = SimpleNamespace(
                port=70000, max_content_length=1, upload_folder=str(upload_dir)
            )
            errors = main_module.validar_configuracao(args, upload_dir)
            self.assertTrue(any("Porta invalida" in err for err in errors))

    def test_validar_configuracao_creates_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            upload_dir = Path(temp_dir) / "uploads"
            args = SimpleNamespace(
                port=5001, max_content_length=1, upload_folder=str(upload_dir)
            )
            errors = main_module.validar_configuracao(args, upload_dir)
            self.assertEqual(errors, [])
            self.assertTrue(upload_dir.exists())

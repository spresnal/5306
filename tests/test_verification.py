"""The unified verifier must propagate component failures and missing coverage."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from property_timeline import verify

ROOT = Path(__file__).resolve().parents[1]


class VerificationTests(unittest.TestCase):
    def check(self, strict=False, node='node', command_ok=True, browser='chrome'):
        result = Mock(skipped=[])
        result.wasSuccessful.return_value = True
        with patch.dict(os.environ), redirect_stdout(io.StringIO()):
            with patch.object(verify.unittest.defaultTestLoader, 'discover', return_value=unittest.TestSuite()), \
                 patch.object(verify.unittest.TextTestRunner, 'run', return_value=result), \
                 patch.object(verify.importlib.util, 'find_spec', return_value=object()), \
                 patch.object(verify.shutil, 'which', return_value=node), \
                 patch.object(verify, 'browser_path', return_value=browser), \
                 patch.object(verify, 'browser_check', return_value=True), \
                 patch.object(verify, 'run_command', return_value=command_ok):
                return verify.main(['--root', str(ROOT)] + (['--strict'] if strict else []))

    def test_javascript_failure_fails_combined_verification(self):
        self.assertEqual(self.check(command_ok=False), 1)

    def test_strict_mode_rejects_missing_prerequisites(self):
        self.assertEqual(self.check(node=None), 0)
        self.assertEqual(self.check(node=None, strict=True), 1)
        self.assertEqual(self.check(browser=None, strict=True), 1)
        self.assertEqual(self.check(strict=True), 0)

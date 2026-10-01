from importlib.metadata import requires
from pathlib import Path
import re
import unittest


class DistributionTests(unittest.TestCase):
    def test_mcp_windows_dependency_is_explicitly_locked(self):
        sdk_requires = requires("mcp") or []
        self.assertTrue(any("pywin32" in r and "win32" in r for r in sdk_requires))
        lock = (Path(__file__).resolve().parents[1] / "requirements.lock.txt").read_text()
        self.assertRegex(lock, r'pywin32==311; sys_platform == "win32"')
        pywin_block = lock.split('pywin32==311', 1)[1].split('\n\n', 1)[0]
        self.assertIn("--hash=sha256:", pywin_block)

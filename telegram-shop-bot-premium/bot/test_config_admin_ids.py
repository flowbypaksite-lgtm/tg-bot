"""
Startup validation tests for ADMIN_IDS parsing in bot/config.py

Each scenario runs `python -c 'import bot.config'` in a subprocess with
a specific ADMIN_IDS value so the test runner is never killed by a
RuntimeError raised at import time.

Scenarios:
  1. Unset ADMIN_IDS         → default 8736699831 used, exits 0
  2. Valid single ID         → exits 0
  3. Valid multiple IDs      → exits 0
  4. Mixed valid+invalid     → valid IDs kept, exits 0
  5. Empty string            → exits non-zero
  6. Whitespace only         → exits non-zero
  7. All non-numeric         → exits non-zero
"""

import os
import subprocess
import sys
import unittest

PYTHON = sys.executable
WORKSPACE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROBE = "import bot.config; print(bot.config.ADMIN_IDS)"


def run(admin_ids):
    """Run the probe script in a subprocess with the given ADMIN_IDS value.
    Pass None to leave the variable unset."""
    env = os.environ.copy()
    env.pop("ADMIN_IDS", None)
    if admin_ids is not None:
        env["ADMIN_IDS"] = admin_ids
    return subprocess.run(
        [PYTHON, "-c", PROBE],
        capture_output=True,
        text=True,
        env=env,
        cwd=WORKSPACE_ROOT,
    )


class TestAdminIdsStartupValidation(unittest.TestCase):

    def test_unset_uses_default(self):
        result = run(None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("8559195254", result.stdout)

    def test_single_valid_id(self):
        result = run("12345678")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("12345678", result.stdout)

    def test_multiple_valid_ids(self):
        result = run("111,222,333")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("111", result.stdout)
        self.assertIn("222", result.stdout)
        self.assertIn("333", result.stdout)

    def test_mixed_keeps_valid_ids(self):
        result = run("999,abc,888")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("999", result.stdout)
        self.assertIn("888", result.stdout)
        self.assertNotIn("abc", result.stdout)

    def test_empty_string_raises(self):
        result = run("")
        self.assertNotEqual(result.returncode, 0)
        combined = result.stderr + result.stdout
        self.assertIn("ADMIN_IDS", combined)

    def test_whitespace_only_raises(self):
        result = run("   ")
        self.assertNotEqual(result.returncode, 0)
        combined = result.stderr + result.stdout
        self.assertIn("ADMIN_IDS", combined)

    def test_all_nonnumeric_raises(self):
        result = run("abc,xyz,foo")
        self.assertNotEqual(result.returncode, 0)
        combined = result.stderr + result.stdout
        self.assertIn("ADMIN_IDS", combined)


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import integration


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / "mcp_config.json"
        self.original = b'{"custom":true,"mcpServers":{"agentMemory":{"command":"keep","env":{"secret":"never-report"}}}}\n'
        self.config.write_bytes(self.original)
        self.registration = {"name": "nexus9", "entry": {"command": "python", "args": ["-m", "nexus9.server"]},
                             "skill_dir": str(self.base / "skills/nexus9"), "workspace": str(self.base / "project"),
                             "replace": False, "install_rule": False}
        self.receipts = self.base / "receipts"

    def install(self):
        return integration.install(self.registration, ROOT, self.config, self.receipts)

    def test_install_preserves_other_servers_and_records_reversible_changes(self):
        installed = self.install()
        current = json.loads(self.config.read_bytes())
        self.assertEqual(current["mcpServers"]["agentMemory"], json.loads(self.original)["mcpServers"]["agentMemory"])
        self.assertTrue((Path(self.registration["skill_dir"]) / "SKILL.md").is_file())
        self.assertEqual(self.install()["status"], "unchanged")
        integration.rollback(installed["receipt"])
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse((Path(self.registration["skill_dir"]) / "SKILL.md").exists())

    def test_rollback_preserves_unrelated_config_changes_after_install(self):
        installed = self.install()
        current = json.loads(self.config.read_bytes())
        current["mcpServers"]["new-server"] = {"command": "also-keep"}
        current["custom"] = "changed-by-user"
        self.config.write_text(json.dumps(current))
        integration.rollback(installed["receipt"])
        rolled = json.loads(self.config.read_bytes())
        self.assertEqual(rolled["mcpServers"]["new-server"]["command"], "also-keep")
        self.assertEqual(rolled["custom"], "changed-by-user")
        self.assertNotIn("nexus9", rolled["mcpServers"])

    def test_rollback_refuses_to_overwrite_user_edited_skill(self):
        installed = self.install()
        skill = Path(self.registration["skill_dir"]) / "SKILL.md"
        skill.write_text("user-edited-skill")
        config = self.config.read_bytes()
        with self.assertRaises(ValueError):
            integration.rollback(installed["receipt"])
        self.assertEqual(self.config.read_bytes(), config)
        self.assertEqual(skill.read_text(), "user-edited-skill")

    def test_mid_install_failure_restores_previous_config(self):
        original_write = integration.atomic_write
        failed = False
        def fail_once(path, payload, expected):
            nonlocal failed
            if Path(path).name == "SKILL.md" and not failed:
                failed = True
                raise OSError("simulated disk failure")
            return original_write(path, payload, expected)
        with patch.object(integration, "atomic_write", side_effect=fail_once):
            with self.assertRaises(ValueError):
                self.install()
        self.assertEqual(self.config.read_bytes(), self.original)
        receipt = next(self.receipts.rglob("receipt.json"))
        self.assertEqual(json.loads(receipt.read_bytes())["status"], "rolled_back")

    def test_existing_skill_conflict_is_detected_before_config_write(self):
        skill = Path(self.registration["skill_dir"]) / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("keep-existing")
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse(self.receipts.exists())

    def test_duplicate_config_keys_are_not_silently_lost(self):
        self.config.write_text('{"mcpServers":{},"mcpServers":{"keep":{}}}')
        before = self.config.read_bytes()
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual(self.config.read_bytes(), before)

    def test_read_only_audit_detects_coexistence_without_exposing_arguments(self):
        data = json.loads(self.original)
        data["mcpServers"]["hydra-tools-mcp"] = {"command": "python", "args": ["private-argument"]}
        self.config.write_text(json.dumps(data))
        rule = self.base / "home/.gemini/GEMINI.md"
        rule.parent.mkdir(parents=True)
        rule.write_text("HYDRA applies\nsecret=private-rule-content")
        before = self.config.read_bytes()
        report = integration.audit(self.config, self.base / "home", self.base / "project")
        self.assertEqual(report["recommended_memory_owner"], "external")
        self.assertEqual(report["recommended_compression_owner"], "external")
        serialized = json.dumps(report)
        for secret in ("never-report", "private-argument", "private-rule-content"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(self.config.read_bytes(), before)

    def test_disabled_hydra_server_does_not_claim_ownership(self):
        self.config.write_text('{"mcpServers":{"hydra-tools-mcp":{"disabled":true}}}')
        report = integration.audit(self.config, self.base / "home", self.base / "project")
        self.assertEqual(report["recommended_memory_owner"], "nexus9")
        self.assertEqual(report["recommended_compression_owner"], "nexus9")

    def test_backup_tampering_stops_rollback_before_any_mutation(self):
        installed = self.install()
        receipt = json.loads(Path(installed["receipt"]).read_bytes())
        Path(next(r["backup"] for r in receipt["files"] if r["kind"] == "config")).write_text("tampered")
        before = self.config.read_bytes()
        with self.assertRaises(ValueError):
            integration.rollback(installed["receipt"])
        self.assertEqual(self.config.read_bytes(), before)

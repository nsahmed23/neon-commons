import json
import tempfile
import unittest
from pathlib import Path

from intune_iac.io import digest, file_sha
from intune_iac.wizard import run_wizard

ROOT = Path(__file__).resolve().parents[1]
POLICY = "22222222-2222-4222-8222-222222222222"
OTHER_POLICY = "33333333-3333-4333-8333-333333333333"


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "export.json"
        self.context = self.root / "context.json"
        self.session = self.root / "session.json"
        self.output = self.root / "project"
        self.fixture("supported")
        self.context.write_bytes((ROOT / "examples/context.json").read_bytes())
        self.messages = []
        self.prompts = []

    def fixture(self, name):
        self.source.write_bytes((ROOT / "examples" / name / "input/export.json").read_bytes())

    def run_script(self, answers, supplied=True):
        queue = iter(answers)

        def read(prompt):
            self.prompts.append(prompt)
            value = next(queue, None)
            if value is None:
                raise EOFError()
            if callable(value):
                value = value()
            return value

        kwargs = {"input_path": self.source, "context_path": self.context, "output_path": self.output} if supplied else {}
        return run_wizard(self.session, input_fn=read, output_fn=self.messages.append, **kwargs)

    def mutate_json(self, path, update):
        value = json.loads(path.read_text())
        update(value)
        path.write_text(json.dumps(value))

    def test_real_intake_generates_verified_project_and_guides_review(self):
        result = self.run_script([str(self.source), str(self.context), str(self.output), "generate", "finish"], supplied=False)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue((self.output / "generated-files.json").is_file())
        self.assertTrue(list(self.output.rglob("*.tf")))
        self.assertIn("Local export path", self.prompts[0])
        self.assertTrue(any(POLICY in line for line in self.messages))
        self.assertTrue(any("Referenced groups and filters remain externally owned" in line for line in self.messages))
        self.assertTrue(any("Review [finish" in line for line in self.prompts))
        self.assertEqual(len(list((self.root / "attempts").glob("*.result.json"))), 2)

    def test_save_resume_rechecks_output_and_completes_local_handoff(self):
        result = self.run_script(["generate", "save"])
        self.assertEqual(result["status"], "suspended")
        result = self.run_script(["finish"], supplied=False)
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["execution_authorized"])
        # A fresh inspection was dispatched on resume; generation was not replayed.
        receipts = [json.loads(p.read_text()) for p in (self.root / "attempts").glob("*.result.json")]
        self.assertEqual(sum(r["action"] == "generate" for r in receipts), 1)
        self.assertEqual(sum(r["action"] == "inspect" for r in receipts), 2)

    def test_source_bytes_changed_at_prompt_prevent_generation(self):
        def change_source():
            self.source.write_bytes(self.source.read_bytes() + b"\n")
            return "generate"

        result = self.run_script([change_source, "save"])
        self.assertEqual(result["status"], "suspended")
        self.assertFalse(self.output.exists())
        self.assertTrue(any("bytes changed" in line for line in self.messages))
        state = json.loads(self.session.read_text())
        self.assertEqual(state["fingerprints"]["input"], file_sha(self.source))

    def test_context_bytes_changed_on_resume_invalidates_generated_review(self):
        self.run_script(["generate", "save"])
        self.context.write_bytes(self.context.read_bytes() + b"\n")
        result = self.run_script(["save"], supplied=False)
        self.assertEqual(result["step"], "preview")
        self.assertFalse(result["generated"])
        self.assertTrue(any("bytes changed" in line for line in self.messages))
        self.assertTrue(self.output.exists())

    def test_manifest_edit_blocks_finish_and_preserves_files(self):
        self.run_script(["generate", "save"])
        manifest = self.output / "generated-files.json"
        changed = manifest.read_bytes() + b"\n"
        manifest.write_bytes(changed)
        result = self.run_script(["review", "cancel"], supplied=False)
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(result["step"], "conflict")
        self.assertEqual(manifest.read_bytes(), changed)
        self.assertTrue(any("Conflict review: output_changed" in line for line in self.messages))

    def test_output_changed_after_review_prompt_cannot_finish(self):
        self.run_script(["generate", "save"])
        target = self.output / "README.md"

        def change_output():
            target.write_text("user-owned edit")
            return "finish"

        result = self.run_script([change_output, "cancel"], supplied=False)
        self.assertEqual(result["step"], "conflict")
        self.assertEqual(target.read_text(), "user-owned edit")

    def test_forged_session_and_manifest_cannot_claim_verified_review(self):
        self.run_script(["generate", "save"])
        target = self.output / "README.md"
        target.write_text("arbitrary forged output")
        manifest = self.output / "generated-files.json"
        self.mutate_json(manifest, lambda value: value["files"].update({"README.md": file_sha(target)}))
        hashes = {p.relative_to(self.output).as_posix(): file_sha(p) for p in self.output.rglob("*") if p.is_file()}
        self.mutate_json(self.session, lambda value: value.update(generated={"manifest_sha256": file_sha(manifest), "tree_sha256": digest(hashes), "file_count": len(hashes)}))
        result = self.run_script(["cancel"], supplied=False)
        self.assertEqual(result["step"], "conflict")
        self.assertEqual(target.read_text(), "arbitrary forged output")
        self.assertTrue(any("verified against current source" in line for line in self.messages))

    def test_unowned_output_conflict_can_use_new_path(self):
        self.output.mkdir()
        target = self.output / "user.txt"
        target.write_text("retain me")
        new_output = self.root / "new-project"
        result = self.run_script(["generate", "review", "new-path", str(new_output), "generate", "finish"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["output"], str(new_output))
        self.assertTrue((new_output / "generated-files.json").is_file())
        self.assertEqual(target.read_text(), "retain me")

    def test_denied_and_missing_relationships_stay_review_only(self):
        for fixture in ("access-denied", "missing-page"):
            with self.subTest(fixture=fixture):
                self.fixture(fixture)
                self.session = self.root / (fixture + ".session.json")
                self.output = self.root / (fixture + "-project")
                result = self.run_script(["generate", "finish"])
                self.assertEqual(result["status"], "complete")
                self.assertFalse(result["execution_authorized"])
                self.assertFalse(list(self.output.rglob("*.tf")))
                self.assertTrue((self.output / "BLOCKED.json").is_file())
                cards = json.loads((self.output / "commands/command-cards.json").read_text())
                self.assertEqual(cards["cards"], [])
        self.assertTrue(any("blocked; review-only" in line for line in self.messages))

    def test_production_export_generates_only_review_artifacts(self):
        self.mutate_json(self.source, lambda value: value.update(synthetic=False, exporter={"id": "company-capture", "version": "1"}))
        result = self.run_script(["generate", "finish"])
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue((self.output / "review/normalized.json").is_file())
        self.assertFalse(list(self.output.rglob("*.tf")))
        self.assertTrue(any("production exports are review-only" in line for line in self.messages))

    def test_policy_selection_uses_uuid_and_own_copy_not_names(self):
        original = self.context.read_bytes()
        result = self.run_script(["select Windows Privacy Pilot", "select " + OTHER_POLICY, "save"])
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(self.context.read_bytes(), original)
        state = json.loads(self.session.read_text())
        selected_context = Path(state["paths"]["context"])
        self.assertNotEqual(selected_context, self.context)
        self.assertEqual(json.loads(selected_context.read_text())["selected_policy_id"], OTHER_POLICY)
        self.assertTrue(any("invalid_policy_id" in line for line in self.messages))
        self.assertTrue(any("blocked; review-only" in line for line in self.messages))
        self.assertFalse(self.output.exists())

    def test_unknown_selection_and_credential_shaped_context_are_rejected(self):
        self.mutate_json(self.context, lambda value: value.update(authorization="CANARY-CREDENTIAL"))
        original = self.context.read_bytes()
        result = self.run_script(["select 99999999-9999-4999-8999-999999999999", "select " + OTHER_POLICY, "save"])
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(self.context.read_bytes(), original)
        self.assertFalse(list(self.root.glob("*.selected-context.*.json")))
        self.assertTrue(any("policy_not_observed" in line for line in self.messages))
        self.assertTrue(any("unsupported_selection_context" in line for line in self.messages))
        self.assertNotIn("CANARY", "\n".join(self.messages) + self.session.read_text())

    def test_production_capture_context_and_repeated_uuid_selection_work(self):
        self.mutate_json(self.source, lambda value: value.update(synthetic=False, exporter={"id": "company-capture", "version": "1"}))
        self.mutate_json(self.context, lambda value: value.update(source_is_synthetic=False, api_version="beta", target_assurance="proposed_reference_labels_only"))
        result = self.run_script(["select " + OTHER_POLICY, "select " + POLICY, "generate", "finish"])
        self.assertEqual(result["status"], "complete")
        state = json.loads(self.session.read_text())
        self.assertEqual(json.loads(Path(state["paths"]["context"]).read_text())["selected_policy_id"], POLICY)
        self.assertEqual(len(list(self.root.glob("*.selected-context.*.json"))), 2)
        self.assertFalse(list(self.output.rglob("*.tf")))

    def test_back_and_edit_reopen_intake_and_reinspect(self):
        new_output = self.root / "edited-project"
        result = self.run_script(["back", str(new_output), "edit context", str(self.context), str(new_output), "generate", "finish"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["output"], str(new_output))
        self.assertFalse(self.output.exists())
        self.assertTrue((new_output / "generated-files.json").is_file())

    def test_eof_and_interrupt_suspend_without_raw_source_or_credentials(self):
        result = self.run_script([])
        self.assertEqual(result["status"], "suspended")

        def interrupt(_prompt):
            raise KeyboardInterrupt()

        result = run_wizard(self.session, input_fn=interrupt, output_fn=self.messages.append)
        self.assertEqual(result["status"], "suspended")
        saved = self.session.read_text()
        self.assertNotIn("Windows Privacy Pilot", saved)
        self.assertNotIn("settingInstance", saved)
        self.assertNotIn("authorization", saved)

    def test_invalid_input_errors_do_not_echo_secret_values(self):
        self.source.write_text('{"CANARY-CREDENTIAL":1,"CANARY-CREDENTIAL":2}')
        result = self.run_script(["generate", "save"])
        self.assertEqual(result["status"], "suspended")
        self.assertFalse(self.output.exists())
        self.assertNotIn("CANARY", "\n".join(self.messages) + self.session.read_text())

    def test_session_cannot_persist_execution_authority(self):
        self.run_script(["save"])
        self.mutate_json(self.session, lambda value: value.update(execution_authorized=True))
        result = self.run_script(["generate", "finish"], supplied=False)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["error"], "invalid_wizard_session")
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

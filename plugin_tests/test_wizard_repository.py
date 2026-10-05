import json
import tempfile
import unittest
from pathlib import Path

from intune_iac.wizard import run_wizard

ROOT = Path(__file__).resolve().parents[1]
POLICY = "22222222-2222-4222-8222-222222222222"
OTHER_POLICY = "33333333-3333-4333-8333-333333333333"
TENANT = "11111111-1111-4111-8111-111111111111"


class RepositoryWizardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "repository"
        (self.repo / "stacks/deploy").mkdir(parents=True)
        (self.repo / "components/terraform/policy").mkdir(parents=True)
        (self.repo / "atmos.yaml").write_text("base_path: .\nstacks:\n  base_path: stacks\n  included_paths: ['deploy/**/*']\ncomponents:\n  terraform:\n    base_path: components/terraform\n")
        self.manifest = self.repo / "stacks/deploy/dev.yaml"
        self.manifest.write_text("vars:\n  region: west\ncomponents:\n  terraform:\n    policy:\n      vars:\n        stage: dev\n")
        self.source = self.root / "export.json"
        self.source.write_bytes((ROOT / "examples/supported/input/export.json").read_bytes())
        self.session = self.root / "session.json"
        self.output = self.root / "project"
        self.messages = []
        self.prompts = []

    def run_script(self, answers, supplied=True, **kwargs):
        queue = iter(answers)

        def read(prompt):
            self.prompts.append(prompt)
            value = next(queue, None)
            if value is None:
                raise EOFError()
            return value() if callable(value) else value

        if supplied:
            kwargs = dict(repo=self.repo, input_path=self.source, output_path=self.output, **kwargs)
        return run_wizard(self.session, input_fn=read, output_fn=self.messages.append, **kwargs)

    def saved(self):
        return json.loads(self.session.read_text())

    def context(self):
        return json.loads(Path(self.saved()["paths"]["context"]).read_text())

    def production(self):
        value = json.loads(self.source.read_text())
        value.update(synthetic=False, exporter={"id": "company-capture", "version": "1"})
        self.source.write_text(json.dumps(value))

    def test_repository_target_creates_owned_context_without_context_prompt(self):
        result = self.run_script(["deploy/dev", "policy", POLICY, "review"])
        self.assertEqual(result["status"], "review_only")
        self.assertFalse(result["execution_authorized"])
        context = self.context()
        self.assertEqual(context["stack"], "deploy/dev")
        self.assertEqual(context["component"], "policy")
        self.assertEqual(context["selected_policy_id"], POLICY)
        self.assertEqual(context["tenant_id"], TENANT)
        self.assertEqual(context["tenant_assurance"], "source_asserted")
        self.assertEqual(context["authorization"], "emit_only")
        self.assertEqual(Path(self.saved()["paths"]["context"]).parent, self.session.parent)
        self.assertFalse(any("context JSON path" in prompt for prompt in self.prompts))
        self.assertTrue(any("source-asserted" in line for line in self.messages))
        self.assertNotIn("settingInstance", self.session.read_text())

    def test_explicit_target_skips_target_prompts_and_default_output_is_usable(self):
        result = self.run_script([POLICY, "", "review"], supplied=False, repo=self.repo,
                                 stack="deploy/dev", component="policy", input_path=self.source)
        self.assertEqual(result["status"], "review_only")
        self.assertEqual(Path(result["output"]), self.root / "intune-proposal")
        self.assertFalse(any(prompt.startswith("Stack") or prompt.startswith("Component") for prompt in self.prompts))
        self.assertTrue(any("default:" in prompt for prompt in self.prompts))

    def test_missing_capture_is_prompted_after_repository_selection(self):
        result = self.run_script(["deploy/dev", "policy", str(self.source), POLICY, "", "review"],
                                 supplied=False, repo=self.repo)
        self.assertEqual(result["status"], "review_only")
        self.assertTrue(self.prompts[0].startswith("Stack"))
        self.assertTrue(self.prompts[1].startswith("Component"))
        self.assertTrue(self.prompts[2].startswith("Local export"))

    def test_synthetic_repository_target_is_visibly_blocked_for_generation(self):
        result = self.run_script(["deploy/dev", "policy", POLICY, "generate", "review"])
        self.assertEqual(result["status"], "review_only")
        self.assertFalse(self.output.exists())
        self.assertTrue(any("syntheticcore_target_unqualified" in line for line in self.messages))
        self.assertTrue(any("blocked; review-only" in line for line in self.messages))

    def test_production_review_can_generate_but_repository_change_invalidates_resume(self):
        self.production()
        first = self.run_script(["deploy/dev", "policy", POLICY, "generate", "save"])
        self.assertTrue(first["generated"])
        self.assertTrue((self.output / "BLOCKED.json").is_file())
        previous_context = self.context()
        self.manifest.write_text(self.manifest.read_text().replace("west", "east"))
        result = self.run_script(["save"], supplied=False)
        self.assertEqual(result["step"], "preview")
        self.assertFalse(result["generated"])
        self.assertNotEqual(previous_context["repository_source_fingerprint"], self.context()["repository_source_fingerprint"])
        self.assertTrue(self.output.exists())
        self.assertTrue(any("Repository" in line and "invalidated" in line for line in self.messages))

    def test_forged_saved_repository_fingerprint_cannot_keep_generated_milestone(self):
        from intune_iac.repository import resolve_component
        self.production()
        self.run_script(["deploy/dev", "policy", POLICY, "generate", "save"])
        self.manifest.write_text(self.manifest.read_text().replace("west", "east"))
        state = self.saved()
        state["repository"]["source_fingerprint"] = resolve_component(self.repo, "deploy/dev", "policy")["source_fingerprint"]
        self.session.write_text(json.dumps(state))
        result = self.run_script(["finish", "save"], supplied=False)
        self.assertEqual(result["status"], "suspended")
        self.assertFalse(result["generated"])
        self.assertEqual(result["step"], "preview")

    def test_policy_reselection_rebuilds_repository_context(self):
        result = self.run_script(["deploy/dev", "policy", POLICY, "select " + OTHER_POLICY, "save"])
        self.assertEqual(result["status"], "suspended")
        self.assertEqual(self.context()["selected_policy_id"], OTHER_POLICY)
        self.assertEqual(self.saved()["repository"]["selected_policy_id"], OTHER_POLICY)
        self.assertEqual(self.context()["stack"], "deploy/dev")

    def test_change_to_dynamic_repository_blocks_previous_generated_completion(self):
        self.production()
        self.run_script(["deploy/dev", "policy", POLICY, "generate", "save"])
        self.manifest.write_text(self.manifest.read_text().replace("west", "'{{ .vars.region }}'"))
        result = self.run_script(["finish", "save"], supplied=False)
        self.assertFalse(result.get("generated", False))
        self.assertNotEqual(result["status"], "complete")
        self.assertTrue(self.output.exists())

    def test_repository_change_at_generation_prompt_requires_reinspection(self):
        self.production()

        def change_repository():
            self.manifest.write_text(self.manifest.read_text().replace("west", "east"))
            return "generate"

        result = self.run_script(["deploy/dev", "policy", POLICY, change_repository, "save"])
        self.assertFalse(result["generated"])
        self.assertFalse(self.output.exists())
        self.assertTrue(any("invalidated" in line for line in self.messages))

    def test_owned_context_edit_cannot_supply_execution_authority(self):
        self.run_script(["deploy/dev", "policy", POLICY, "save"])
        context_path = Path(self.saved()["paths"]["context"])
        value = json.loads(context_path.read_text())
        value.update(authorization="execute", tenant_id="99999999-9999-4999-8999-999999999999")
        context_path.write_text(json.dumps(value))
        result = self.run_script(["review"], supplied=False)
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(self.context()["authorization"], "emit_only")
        self.assertEqual(self.context()["tenant_id"], TENANT)
        self.assertNotEqual(Path(self.saved()["paths"]["context"]), context_path)

    def test_plugin_capture_generates_only_inactive_repository_candidate(self):
        value = json.loads(self.source.read_text())
        value.update(synthetic=False, exporter={"id": "intune-iac-settings-catalog-graph", "version": "1.0.0"}, references=[], ownership=[])
        for assignment in value["collections"][2]["pages"][0]["body"]["value"]:
            assignment.update(source="direct", sourceId=None)
        self.source.write_text(json.dumps(value))
        result = self.run_script(["deploy/dev", "policy", POLICY, "generate", "finish"])
        self.assertEqual(result["status"], "complete")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue((self.output / "candidates/components/terraform/policy/main.tf.txt").is_file())
        self.assertFalse(list(self.output.rglob("*.tf")))
        cards = json.loads((self.output / "commands/command-cards.json").read_text())
        self.assertEqual(cards["cards"], [])

    def test_explicit_abstract_component_cannot_create_owned_context(self):
        self.manifest.write_text(self.manifest.read_text().replace("    policy:\n", "    policy:\n      metadata: {type: abstract}\n"))
        result = self.run_script([POLICY, "save"], stack="deploy/dev", component="policy")
        self.assertFalse(result["generated"])
        self.assertNotIn("context", self.saved()["paths"])
        self.assertTrue(any("repository_target_not_selectable" in line for line in self.messages))

    def test_helmfile_component_is_never_an_intune_target(self):
        self.manifest.write_text(self.manifest.read_text().replace("  terraform:", "  helmfile:"))
        result = self.run_script([POLICY, "save"], stack="deploy/dev", component="policy")
        self.assertFalse(result["generated"])
        self.assertNotIn("context", self.saved()["paths"])
        self.assertTrue(any("repository_target_not_selectable" in line for line in self.messages))

    def test_malformed_capture_inventory_suspends_without_copying_source(self):
        self.source.write_text('{"collections": null, "private": "capture-secret-canary"}')
        result = self.run_script(["save"], stack="deploy/dev", component="policy")
        self.assertEqual(result["status"], "suspended")
        self.assertNotIn("context", self.saved()["paths"])
        self.assertNotIn("capture-secret-canary", "\n".join(self.messages) + self.session.read_text())


if __name__ == "__main__":
    unittest.main()

"""Original offline material checks, not native host/provider validation."""
import csv
import hashlib
import json
import sys
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reference.core import classify_plan, evidence_summary, generate_files, normalize
from reference.invariants import compare


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class AdditionalMaterials(unittest.TestCase):
    def test_diagnostic_evidence_has_valid_contract(self):
        schema = read_json("contracts/evidence.schema.json")
        evidence = read_json("examples/diagnostics/input/evidence.json")
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(evidence)
        self.assertTrue(evidence["synthetic"])
        self.assertTrue(evidence["capture"]["truncated"])
        self.assertIsNone(evidence["capture"]["logging_enabled"])

    def test_denominator_fixture_matches_expected_arithmetic(self):
        fixture = read_json("examples/diagnostics/input/eight-reporters.json")
        expected = read_json("examples/diagnostics/expected/eight-reporters-summary.json")
        actual = evidence_summary(fixture["targeted"], fixture["rows"])
        self.assertEqual(actual, expected)
        self.assertEqual(actual["successful"], 8)
        self.assertEqual(actual["unknown"], 92)
        self.assertFalse(actual["promotion_proven"])

    def test_plan_fixtures_are_explicitly_synthetic(self):
        paths = sorted((ROOT / "evaluations/plans").glob("*.synthetic.json"))
        self.assertEqual(len(paths), 5)
        for path in paths:
            with self.subTest(plan=path.name):
                plan = json.loads(path.read_text(encoding="utf-8"))
                expected = json.loads(path.with_name(path.name.replace(".synthetic", ".expectation")).read_text(encoding="utf-8"))
                self.assertTrue(expected["synthetic"])
                self.assertFalse(expected["observed_provider_run"])
                self.assertFalse(expected["execution_authorized"])
                actions = plan["resource_changes"][0]["change"]["actions"]
                actual = classify_plan(actions, expected.get("required_source_contract"))
                self.assertEqual(actual, expected["expected_advisory_class"])

    def test_source_lock_and_records_are_internally_consistent(self):
        lock = read_json("source-lock.json")
        Draft202012Validator(read_json("contracts/source-lock.schema.json")).validate(lock)
        sources = {source["id"]: source for source in lock["sources"]}
        units = [json.loads(line) for line in (ROOT / "code-catalog.jsonl").read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(units), len({unit["id"] for unit in units}))
        for unit in units:
            with self.subTest(unit=unit["id"]):
                self.assertIn(unit["source_id"], sources)
                self.assertEqual(unit["commit_sha"], sources[unit["source_id"]]["commit_sha"])
                self.assertEqual(read_json(unit["local_record"]), unit)
                if not unit["raw_bytes_acquired"]:
                    self.assertIsNone(unit["raw_bytes_sha256"])

    def test_packaging_examples_share_identity(self):
        root = read_json("examples/host-package/plugin.json")
        codex = read_json("examples/host-package/.codex-plugin/plugin.json")
        claude = read_json("examples/host-package/.claude-plugin/plugin.json")
        for key in ["name", "version", "description"]:
            self.assertEqual(root[key], codex[key])
            self.assertEqual(root[key], claude[key])
        self.assertEqual(codex["skills"], "./skills/")
        skill = ROOT / "examples/host-package/skills/package-contract/SKILL.md"
        self.assertTrue(skill.is_file())
        self.assertTrue((skill.parent / "references/boundary.md").is_file())
        # These checks establish local identity/path consistency only.

    def test_codex_benchmark_shape_is_not_legacy_responses(self):
        config = read_json("evaluations/plugin-eval.native-example.json")
        self.assertEqual(config["kind"], "plugin-eval-benchmark")
        self.assertEqual(config["schemaVersion"], 2)
        self.assertEqual(config["runner"]["type"], "codex-cli")
        self.assertEqual(config["targetProvisioning"]["mode"], "workspace-plugin-marketplace")
        self.assertTrue((ROOT / config["workspace"]["sourcePath"]).is_dir())
        self.assertFalse({"harnessPrompt", "baseUrl", "apiKeyEnv"} & config.keys())
        self.assertNotIn("model", config["runner"])  # explicitly unresolved, not a hidden default

    def test_claude_example_declares_actual_local_paths(self):
        base = ROOT / "evaluations/claude-native/partial-adoption"
        config = yaml.safe_load((base / "case.yaml").read_text(encoding="utf-8"))
        self.assertEqual(str(config["schema_version"]), "1.1")
        self.assertTrue((base / "prompt.md").is_file())
        for path in config["context"]["add_dirs"]:
            self.assertTrue((base / path).is_dir())
        self.assertTrue(any((base / "graders").iterdir()))

    def test_all_generated_project_manifest_hashes_match(self):
        manifests = sorted(ROOT.glob("examples/*/expected/project/generated-files.json"))
        self.assertEqual(len(manifests), 5)
        for path in manifests:
            with self.subTest(project=str(path.relative_to(ROOT))):
                record = json.loads(path.read_text(encoding="utf-8"))
                declared = record["files"]
                for name, expected in declared.items():
                    file = path.parent / name
                    self.assertTrue(file.is_file())
                    self.assertFalse(file.is_symlink())
                    self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(), expected)
                actual = {str(p.relative_to(path.parent)).replace("\\", "/") for p in path.parent.rglob("*") if p.is_file()}
                self.assertEqual(actual, set(declared) | {"generated-files.json"})

    def test_corpus_inventory_is_not_reported_as_full_audit(self):
        corpus = read_json("catalog-manifest.json")
        paths = [row["declared_path"] for row in corpus["labs"]]
        self.assertEqual(len(paths), 88)
        self.assertEqual(len(set(paths)), 88)
        self.assertEqual(corpus["declared_count"], len(paths))
        self.assertEqual(corpus["fully_audited_count"], 0)
        self.assertEqual(corpus["executed_count"], 0)
        self.assertTrue(all(row["inventory_status"] == "declaration_only" for row in corpus["labs"]))

    def test_all_golden_outputs_reproduce_from_current_algorithms(self):
        context = read_json("examples/context.json")
        for variant in ["supported", "partial", "missing-page", "access-denied"]:
            with self.subTest(variant=variant):
                source = read_json(f"examples/{variant}/input/export.json")
                actual = normalize(source, context["selected_policy_id"], context["tenant_id"])
                self.assertEqual(actual, read_json(f"examples/{variant}/expected/normalized.json"))
                generated = generate_files(actual, context)
                raw = (ROOT / f"examples/{variant}/input/export.json").read_bytes()
                generated["adoption/source-receipt.json"] = json.dumps({
                    "schema_version": "1.0.0",
                    "source_byte_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_canonical_sha256": actual["source_canonical_sha256"],
                }, indent=2, sort_keys=True) + "\n"
                self.assertEqual(compare(raw, actual, files=generated, context=context), [])
                project = ROOT / "examples" / variant / "expected/project"
                manifest = json.loads((project / "generated-files.json").read_text(encoding="utf-8"))
                self.assertEqual(set(generated), set(manifest["files"]))
                for name, content in generated.items():
                    self.assertEqual(content, (project / name).read_text(encoding="utf-8"))

    def test_gap_evidence_paths_and_trace_assertions_exist(self):
        gaps = read_json("gap-register.json")["gaps"]
        self.assertEqual({row["id"] for row in gaps}, {f"G{i:02d}" for i in range(1, 13)})
        for gap in gaps:
            for name in gap["artifacts"]:
                self.assertTrue((ROOT / name).exists(), f"{gap['id']}: {name}")
        with (ROOT / "requirements-traceability.csv").open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                self.assertTrue((ROOT / row["assertion_file"]).is_file(), row["assertion_file"])


if __name__ == "__main__":
    unittest.main()

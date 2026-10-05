"""Real stdlib HTTP serialization tests, with synthetic CLM probabilities."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from intune_iac.judge import assess, CRITERIA, INSTRUCTIONS, QUESTION_ID


def response(probabilities=None):
    probabilities = probabilities or {"supported": .9, "contradicted": .05, "insufficient": .05}
    top = max(probabilities, key=probabilities.get)
    confidence = probabilities[top] - (sum(probabilities.values()) - probabilities[top]) / 2
    return {"model": "pinned-intune", "answers": {QUESTION_ID: {"type": "choice", "choice": top,
            "confidence": confidence, "probabilities": probabilities}}, "usage": {"output_tokens": 0}}


class JudgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.requests = []
        self.reply = response()
        self.status = 200
        self.delay = 0
        self.redirect = None
        self.on_request = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                owner.requests.append({"path": self.path, "body": json.loads(raw),
                                       "authorization": self.headers.get("Authorization")})
                if owner.on_request:
                    owner.on_request()
                time.sleep(owner.delay)
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                if owner.redirect:
                    self.send_header("Location", owner.redirect)
                self.end_headers()
                raw_reply = owner.reply if isinstance(owner.reply, bytes) else json.dumps(owner.reply).encode()
                try:
                    self.wfile.write(raw_reply)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()
        tokenizer = {"normalizer": None, "pre_tokenizer": {"type": "Sequence", "pretokenizers": [
            {"type": "Split", "pattern": {"Regex": "a"}, "behavior": "Isolated", "invert": False},
            {"type": "ByteLevel", "add_prefix_space": False, "use_regex": False}]},
            "post_processor": None, "model": {"type": "BPE", "byte_fallback": False}}
        self.tokenizer = self.root / "tokenizer.json"
        self.tokenizer.write_text(json.dumps(tokenizer))
        self.head = self.root / "head.pt"
        self.head.write_bytes(b"synthetic-head-no-inference")
        self.config = {"version": 1, "endpoint": f"http://127.0.0.1:{self.server.server_port}/v1/systemone",
            "timeout_seconds": 1, "model_identity": {"alias": "pinned-intune", "clm_source_commit": "a"*40,
            "encoder": "Qwen/Qwen3-8B", "encoder_revision": "b"*40,
            "tokenizer_sha256": hashlib.sha256(self.tokenizer.read_bytes()).hexdigest(),
            "head_sha256": hashlib.sha256(self.head.read_bytes()).hexdigest(), "head_path": "head.pt",
            "pooling": "last-token", "embedding_service_identity": "synthetic-test-service",
            "embedding_recipe": "raw_tokenizer_no_template", "projection": "synthetic-projection",
            "logit_scale": 10, "dtype": "float32", "quantization": "none", "embedding_width": 4096, "temperature": 1},
            "token_budget": {"method": "qwen3_byte_bpe_upper_bound_v1", "tokenizer_path": "tokenizer.json",
                             "encoder_max_tokens": 2048, "clm_max_tokens": 2048},
            "selection": {"min_probability": .8, "min_margin": .2}}
        self.path = self.root / "config.json"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def call(self, claim="The setting is enabled.", evidence=None):
        self.path.write_text(json.dumps(self.config))
        return assess(self.path, claim, evidence if evidence is not None else [{"id": "record-1", "text": "enabled"}])

    def assert_safe(self, result, reason=None):
        self.assertEqual(result["verdict"], "insufficient")
        self.assertFalse(result["execution_authorized"])
        self.assertTrue(result["advisory_only"])
        json.dumps(result, allow_nan=False)
        if reason:
            self.assertEqual(result["reason_code"], reason)

    def test_actual_wire_protocol_and_exact_rendered_binding(self):
        result = self.call()
        self.assertEqual(result["status"], "assessed")
        self.assertEqual(result["verdict"], "supported")
        request = self.requests[0]
        self.assertEqual(request["path"], "/v1/systemone")
        self.assertEqual(set(request["body"]), {"state", "model", "temperature", "questions"})
        question = request["body"]["questions"][QUESTION_ID]
        self.assertEqual(question, {"type": "choice", "instructions": INSTRUCTIONS, "criteria": CRITERIA})
        self.assertEqual(list(question["criteria"]), ["supported", "contradicted", "insufficient"])
        rendered = request["body"]["state"].strip() + "\n\n" + INSTRUCTIONS.strip()
        self.assertEqual(result["rendered_state_sha256"], hashlib.sha256(rendered.encode()).hexdigest())
        self.assertEqual(result["token_preflight"]["per_text_upper_bounds"][0], len(rendered.encode()))
        self.assertAlmostEqual(result["candidate_relative_confidence"], .85)
        self.assertFalse(result["observed_model_identity"]["weights_authenticated"])
        self.assertFalse(result["execution_authorized"])
        self.assertNotIn("rationale", result)
        self.assertNotIn("citations", result)

    def test_contradiction_is_advisory(self):
        self.reply = response({"supported": .02, "contradicted": .93, "insufficient": .05})
        result = self.call()
        self.assertEqual(result["verdict"], "contradicted")
        self.assertFalse(result["execution_authorized"])

    def test_ties_and_uncertain_and_insufficient_abstain(self):
        for probabilities in ({"supported": .5, "contradicted": .5, "insufficient": 0},
                              {"supported": .6, "contradicted": .3, "insufficient": .1},
                              {"supported": .01, "contradicted": .04, "insufficient": .95}):
            with self.subTest(probabilities=probabilities):
                self.reply = response(probabilities)
                result = self.call()
                self.assert_safe(result)
                self.assertEqual(result["status"], "abstained")
                self.assertEqual(result["probabilities"], probabilities)

    def test_malformed_distributions_never_pass(self):
        cases = []
        for probabilities in ({"supported": 1},
                              {"supported": .9, "contradicted": .1, "insufficient": .1},
                              {"supported": 1.1, "contradicted": -.1, "insufficient": 0},
                              {"supported": True, "contradicted": 0, "insufficient": 0},
                              {"supported": float("nan"), "contradicted": 0, "insufficient": 0}):
            value = response()
            value["answers"][QUESTION_ID]["probabilities"] = probabilities
            cases.append(value)
        for field, value in (("choice", "invented"), ("confidence", .99), ("type", "noul")):
            candidate = response()
            candidate["answers"][QUESTION_ID][field] = value
            cases.append(candidate)
        for candidate in cases:
            with self.subTest(candidate=candidate):
                self.reply = candidate
                self.assert_safe(self.call())

    def test_wrong_model_question_id_and_choice_are_rejected(self):
        self.reply = response()
        self.reply["model"] = "other-head"
        self.assert_safe(self.call(), "response_model_mismatch")
        self.reply = response()
        self.reply["answers"]["another"] = self.reply["answers"].pop(QUESTION_ID)
        self.assert_safe(self.call(), "malformed_response")
        self.reply = response()
        self.reply["answers"][QUESTION_ID]["choice"] = "contradicted"
        self.assert_safe(self.call(), "malformed_response")

    def test_duplicate_nonfinite_oversize_and_invalid_json(self):
        for raw in (b'{"model":"x","model":"pinned-intune"}', b'{"number":NaN}', b'not json', b' '*65537):
            with self.subTest(raw_length=len(raw)):
                self.reply = raw
                self.assert_safe(self.call())

    def test_redirect_never_receives_credentials(self):
        self.config["api_key_env"] = "CLM_TEST_KEY"
        self.status = 302
        self.redirect = self.config["endpoint"] + "?exfiltrate=yes"
        with patch.dict(os.environ, {"CLM_TEST_KEY": "secret-test-value"}):
            result = self.call()
        self.assert_safe(result, "redirect_rejected")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["authorization"], "Bearer secret-test-value")
        self.assertNotIn("secret-test-value", json.dumps(result))

    def test_plaintext_remote_and_url_credentials_are_rejected_before_network(self):
        for endpoint in ("http://example.com/v1/systemone", "https://example.com/v1/systemone",
                         "http://name:password@127.0.0.1/v1/systemone",
                         "http://127.0.0.1/v1/systemone?x=1", "file:///v1/systemone"):
            with self.subTest(endpoint=endpoint):
                self.config["endpoint"] = endpoint
                self.assert_safe(self.call(), "unsafe_endpoint")
        self.assertEqual(self.requests, [])

    def test_timeout_and_http_error_and_unreachable(self):
        self.config["timeout_seconds"] = .05
        self.delay = .15
        self.assert_safe(self.call(), "timeout")
        self.delay = 0
        self.status = 503
        self.assert_safe(self.call(), "http_error")
        self.config["endpoint"] = "http://127.0.0.1:0/v1/systemone"
        self.assert_safe(self.call(), "service_unavailable")

    def test_no_silent_truncation_of_state_or_candidates(self):
        self.config["token_budget"]["clm_max_tokens"] = 100
        self.assert_safe(self.call(), "input_would_exceed_token_bound")
        self.config["token_budget"]["clm_max_tokens"] = 2048
        self.assert_safe(self.call(evidence={"text": "é"*1800}), "input_would_exceed_token_bound")
        self.assertEqual(self.requests, [])

    def test_unsupported_tokenizer_and_changed_pins_prevent_http(self):
        tokenizer = json.loads(self.tokenizer.read_text())
        tokenizer["normalizer"] = {"type": "NFKC"}
        self.tokenizer.write_text(json.dumps(tokenizer))
        self.assert_safe(self.call(), "tokenizer_identity_mismatch")
        self.config["model_identity"]["tokenizer_sha256"] = hashlib.sha256(self.tokenizer.read_bytes()).hexdigest()
        self.assert_safe(self.call(), "token_bound_unavailable")
        self.head.write_bytes(b"changed-head")
        self.assert_safe(self.call(), "head_identity_mismatch")
        self.assertEqual(self.requests, [])

    def test_missing_local_artifact_and_unpinned_identity(self):
        self.config["model_identity"]["encoder_revision"] = "main"
        self.assert_safe(self.call(), "invalid_identity_pin")
        self.config["model_identity"]["encoder_revision"] = "b"*40
        self.tokenizer.unlink()
        self.assert_safe(self.call())
        self.assertEqual(self.requests, [])

    def test_head_changed_during_request_and_credential_errors_fail_safe(self):
        self.on_request = lambda: self.head.write_bytes(b"replaced-while-serving")
        self.assert_safe(self.call(), "head_changed_during_request")
        self.on_request = None
        self.head.write_bytes(b"synthetic-head-no-inference")
        self.config["api_key_env"] = "HOME"
        self.assert_safe(self.call(), "invalid_credential_config")
        self.config["api_key_env"] = "CLM_MISSING_TEST_KEY"
        with patch.dict(os.environ, {}, clear=True):
            self.assert_safe(self.call(), "credential_unavailable")
        self.assertEqual(len(self.requests), 1)

    def test_complex_nonjson_evidence_rejected_and_response_does_not_supply_proof(self):
        nested = {"a": 1}
        for _ in range(33):
            nested = {"a": nested}
        for evidence in (nested, {1: "numeric-key"}, {"tuple": (1, 2)}, {"values": [0]*8192}):
            self.assert_safe(self.call(evidence=evidence))
        self.assertEqual(self.requests, [])
        self.reply["rationale"] = "fabricated server explanation"
        self.reply["citations"] = ["fabricated citation"]
        result = self.call()
        self.assertNotIn("rationale", result)
        self.assertNotIn("citations", result)

    def test_tokenizer_must_have_no_expanding_operations(self):
        original = json.loads(self.tokenizer.read_text())
        mutations = (
            lambda value: value["pre_tokenizer"]["pretokenizers"][-1].update(add_prefix_space=True),
            lambda value: value.update(post_processor={"type": "TemplateProcessing"}),
            lambda value: value["model"].update(byte_fallback=True),
            lambda value: value["model"].update(continuing_subword_prefix="##"),
        )
        for mutate in mutations:
            value = json.loads(json.dumps(original))
            mutate(value)
            self.tokenizer.write_text(json.dumps(value))
            self.config["model_identity"]["tokenizer_sha256"] = hashlib.sha256(self.tokenizer.read_bytes()).hexdigest()
            self.assert_safe(self.call(), "token_bound_unavailable")
        self.assertEqual(self.requests, [])

    def test_input_is_bounded_and_empty_claim_rejected(self):
        for claim, evidence in (("", {}), ("a"*4097, {}), ("claim", "unstructured"),
                                ("claim", {"value": float("inf")}), ("claim", {"value": "x"*65537})):
            with self.subTest(claim_length=len(claim)):
                self.assert_safe(self.call(claim, evidence))
        self.assertEqual(self.requests, [])

    def test_changed_evidence_and_identity_change_receipt(self):
        first = self.call(evidence={"value": "yes"})
        second = self.call(evidence={"value": "no"})
        self.assertNotEqual(first["rendered_state_sha256"], second["rendered_state_sha256"])
        self.assertNotEqual(first["evidence_sha256"], second["evidence_sha256"])
        self.assertEqual(first["candidate_set_sha256"], second["candidate_set_sha256"])
        self.config["model_identity"]["temperature"] = .5
        third = self.call(evidence={"value": "no"})
        self.assertNotEqual(second["model_config_sha256"], third["model_config_sha256"])
        self.assertNotEqual(second["request_sha256"], third["request_sha256"])


if __name__ == "__main__":
    unittest.main()

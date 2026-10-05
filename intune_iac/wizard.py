"""Interactive, local-only source inspection and proposal generation.

Sessions are restart hints and byte consistency evidence, never approvals. The
runner remains the only dispatcher and the engine remains the mapping authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from uuid import UUID, uuid4

from . import engine, runner
from .io import AppError, digest, file_sha, load_json, write_json

_STEPS = {"stack", "component", "policy", "source", "context", "output", "inspect", "preview", "review", "conflict"}
_CONTEXT_KEYS = {
    "schema_version", "tenant_id", "cloud", "engine", "engine_version",
    "atmos_version", "provider_source", "provider_version", "component", "stack",
    "repository_revision", "source_is_synthetic", "authorization", "backend_owner",
    "state_key", "selected_policy_id",
    "api_version", "target_assurance",
}
_SESSION_KEYS = {
    "schema_version", "step", "paths", "fingerprints", "generated", "conflict_reason",
}


def _code(error):
    value = getattr(error, "code", "local_operation_failed")
    return value if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,80}", value) else "local_operation_failed"


def _outcome(result):
    """Extract an engine result without treating a rejected receipt as success."""
    if result.get("status") != "succeeded_verified":
        error = result.get("error", {})
        code = error.get("code", "action_rejected") if isinstance(error, dict) else "action_rejected"
        if not isinstance(code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,80}", code):
            code = "action_rejected"
        raise AppError(code, "The local action did not complete with verified evidence.")
    value = result.get("result")
    if not isinstance(value, dict):
        raise AppError("invalid_action_result", "The local action result is invalid.")
    return value


def _fingerprints(paths):
    return {name: file_sha(paths[name]) for name in ("input", "context")}


def _output_snapshot(path):
    """Hash every output byte, including the ownership manifest and extra files."""
    root = Path(path)
    if not root.exists() and not root.is_symlink():
        return None
    if root.is_symlink() or not root.is_dir() or any(p.is_symlink() for p in root.parents):
        raise AppError("unsafe_output_path", "Output must be a regular local directory.")
    files = {}
    for item in sorted(root.rglob("*")):
        if item.is_symlink():
            raise AppError("unsafe_output_path", "Output contains a symbolic link.")
        if item.is_file():
            if len(files) >= 4096:
                raise AppError("unsafe_output_path", "Output exceeds bounded local review limits.")
            files[item.relative_to(root).as_posix()] = file_sha(item)
        elif not item.is_dir():
            raise AppError("unsafe_output_path", "Output contains a special file.")
    return {"manifest_sha256": files.get("generated-files.json"), "tree_sha256": digest(files), "file_count": len(files)}


def _session(path):
    if not Path(path).exists():
        return {"schema_version": "1.0.0", "step": "source", "paths": {}, "fingerprints": {}, "generated": None, "conflict_reason": None}
    value = load_json(path)
    _validate_session_header(value)
    _validate_session_paths(value["paths"])
    _validate_session_fingerprints(value["fingerprints"])
    _validate_session_generated(value["generated"])
    _validate_session_checkpoint(value)
    if "repository" in value:
        _validate_session_repository(value["repository"])
    elif value["step"] in {"stack", "component", "policy"}:
        raise AppError("invalid_wizard_session", "Repository selection requires a repository.")
    return value


def _validate_session_header(value):
    if not isinstance(value, dict) or set(value) not in (_SESSION_KEYS, _SESSION_KEYS | {"repository"}) or value.get("schema_version") != "1.0.0" or value.get("step") not in _STEPS:
        raise AppError("invalid_wizard_session", "Session is not a supported local wizard record.")


def _validate_session_paths(paths):
    if not isinstance(paths, dict) or not set(paths) <= {"input", "context", "output"} or any(not isinstance(p, str) or not p for p in paths.values()):
        raise AppError("invalid_wizard_session", "Session paths are invalid.")


def _validate_session_fingerprints(fingerprints):
    if not isinstance(fingerprints, dict) or not set(fingerprints) <= {"input", "context"} or any(not isinstance(h, str) or not re.fullmatch(r"[0-9a-f]{64}", h) for h in fingerprints.values()):
        raise AppError("invalid_wizard_session", "Session fingerprints are invalid.")


def _validate_session_generated(generated):
    if generated is None:
        return
    if not isinstance(generated, dict) or set(generated) != {"manifest_sha256", "tree_sha256", "file_count"}:
        raise AppError("invalid_wizard_session", "Session output evidence is invalid.")
    valid_hashes = all(isinstance(generated.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", generated[key]) for key in ("manifest_sha256", "tree_sha256"))
    if not valid_hashes or type(generated.get("file_count")) is not int:
        raise AppError("invalid_wizard_session", "Session output evidence is invalid.")


def _validate_session_checkpoint(value):
    if value.get("conflict_reason") not in (None, "output_changed", "output_conflict", "outcome_unknown"):
        raise AppError("invalid_wizard_session", "Session conflict is invalid.")
    if value["step"] == "review":
        _validate_review_checkpoint(value)
    if value["step"] == "conflict" and value["conflict_reason"] is None:
        raise AppError("invalid_wizard_session", "A conflict checkpoint requires a reason.")


def _validate_review_checkpoint(value):
    if value["generated"] is None or set(value["paths"]) != {"input", "context", "output"} or set(value["fingerprints"]) != {"input", "context"}:
        raise AppError("invalid_wizard_session", "Generated review requires recorded output and source evidence.")


def _validate_session_repository(repository):
    if not isinstance(repository, dict) or set(repository) != {"root", "stack", "component", "selected_policy_id", "source_fingerprint"}:
        raise AppError("invalid_wizard_session", "Repository restart hints are invalid.")
    if not isinstance(repository["root"], str) or not repository["root"]:
        raise AppError("invalid_wizard_session", "Repository selection is invalid.")
    _validate_repository_selectors(repository)
    fingerprint = repository["source_fingerprint"]
    if fingerprint is not None and (not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        raise AppError("invalid_wizard_session", "Repository fingerprint is invalid.")


def _validate_repository_selectors(repository):
    if any(repository[key] is not None and (not isinstance(repository[key], str) or not repository[key] or len(repository[key]) > 1024) for key in ("stack", "component", "selected_policy_id")):
        raise AppError("invalid_wizard_session", "Repository selection is invalid.")


def _policy_ids(input_path):
    source = load_json(input_path)
    ids = set()
    if isinstance(source, dict) and isinstance(source.get("collections"), list):
        for collection in source["collections"]:
            if isinstance(collection, dict) and collection.get("kind") == "policies":
                pages = collection.get("pages")
                for page in pages if isinstance(pages, list) else []:
                    body = page.get("body", {}) if isinstance(page, dict) else {}
                    values = body.get("value") if isinstance(body, dict) else None
                    for item in values if isinstance(values, list) else []:
                        if isinstance(item, dict) and isinstance(item.get("id"), str):
                            try:
                                ids.add(str(UUID(item["id"])))
                            except ValueError:
                                pass
    return ids


def _selected_context(session_path, paths, selected):
    try:
        policy_id = str(UUID(selected))
    except (ValueError, AttributeError):
        raise AppError("invalid_policy_id", "Selection requires a policy UUID, not a display name.") from None
    ids = _policy_ids(paths["input"])
    if policy_id not in ids:
        raise AppError("policy_not_observed", "Selected ID is not present in the local policy inventory.")
    context = load_json(paths["context"])
    if not isinstance(context, dict) or not set(context) <= _CONTEXT_KEYS:
        raise AppError("unsupported_selection_context", "Use a bounded context file before selecting another ID.")
    _validate_selection_context(context)
    context = dict(context, selected_policy_id=policy_id)
    own_path = Path(session_path).parent / (Path(session_path).name + ".selected-context." + uuid4().hex + ".json")
    if own_path.absolute() in {Path(p).absolute() for p in paths.values()}:
        raise AppError("context_copy_conflict", "The session context copy conflicts with an input path.")
    write_json(own_path, context)
    return str(own_path.absolute())


def _validate_selection_context(context):
    pinned = {
        "schema_version": "1.0.0", "cloud": "public", "engine": "tofu",
        "engine_version": "1.10.0", "atmos_version": "1.199.0",
        "provider_source": "deploymenttheory/microsoft365", "provider_version": "1.0.0",
        "component": "intune-reference", "stack": "reference-dev", "authorization": "emit_only",
        "backend_owner": "external", "api_version": "beta",
        "target_assurance": "proposed_reference_labels_only",
    }
    valid = all(context[k] == expected for k, expected in pinned.items() if k in context)
    valid = valid and ("source_is_synthetic" not in context or type(context["source_is_synthetic"]) is bool)
    valid = valid and _optional_context_pattern(context, "repository_revision", r"[0-9a-f]{40}")
    valid = valid and _optional_context_pattern(context, "state_key", r"[A-Za-z0-9_./-]{1,256}")
    try:
        for field in ("tenant_id", "selected_policy_id"):
            if not isinstance(context.get(field), str):
                valid = False
            else:
                UUID(context[field])
    except ValueError:
        valid = False
    if not valid:
        raise AppError("unsupported_selection_context", "Context values exceed the bounded local selection format.")


def _optional_context_pattern(context, key, pattern):
    return key not in context or isinstance(context[key], str) and bool(re.fullmatch(pattern, context[key]))


def _repository_context(repository, input_path):
    """Reconstruct target intent from live evidence, never saved resolution claims."""
    from .repository import resolve_component
    resolved = resolve_component(repository["root"], repository["stack"], repository["component"])
    if resolved.get("status") != "resolved":
        raise AppError("repository_target_blocked", "Repository target could not be resolved from literal sources.")
    if resolved.get("abstract") is not False or resolved.get("kind") != "terraform":
        raise AppError("repository_target_not_selectable", "Select a concrete Terraform component for Intune target intent.")
    source = load_json(input_path)
    if not isinstance(source, dict) or type(source.get("synthetic")) is not bool or source.get("cloud") != "public":
        raise AppError("invalid_capture", "A complete supported local capture is required.")
    try:
        tenant = str(UUID(source["tenant_id"]))
        selected = str(UUID(repository["selected_policy_id"]))
    except (KeyError, ValueError, AttributeError, TypeError):
        raise AppError("invalid_capture_identity", "Capture and policy UUIDs must be valid.") from None
    if selected not in _policy_ids(input_path):
        raise AppError("policy_not_observed", "Select a policy UUID observed in this capture.")
    return {
        "schema_version": "1.0.0", "tenant_id": tenant, "cloud": source["cloud"],
        "tenant_assurance": "source_asserted", "selected_policy_id": selected,
        "stack": resolved["stack"], "component": resolved["component"],
        "implementation": resolved["implementation"], "authorization": "emit_only",
        "source_is_synthetic": source["synthetic"],
        "target_assurance": "repository_literal_resolution_only",
        "repository_source_fingerprint": resolved["source_fingerprint"],
    }


def _write_repository_context(session_path, context):
    path = session_path.parent / (session_path.name + ".repository-context." + uuid4().hex + ".json")
    write_json(path, context)
    return str(path)


def _local_path(value):
    path = Path(value).absolute()
    if any(candidate.is_symlink() for candidate in [path, *path.parents]):
        raise AppError("unsafe_path", "Symlinked wizard paths are not supported.")
    return path.resolve()


def _validate_scopes(session_path, paths):
    """Reject self-created ownership conflicts before persisting session state."""
    session = _local_path(session_path)
    resolved = {name: _local_path(path) for name, path in paths.items() if path is not None}
    attempts = session.parent / "attempts"
    for name in ("input", "context"):
        source = resolved.get(name)
        if source is not None and (source == session or source in session.parents or source == attempts or source in attempts.parents):
            raise AppError("wizard_path_conflict", "Session persistence overlaps a source path.")
    output = resolved.get("output")
    if output is not None:
        protected = [session, attempts, *(resolved[name] for name in ("input", "context") if name in resolved)]
        if any(output == path or output in path.parents for path in protected):
            raise AppError("wizard_path_conflict", "Output must not contain session, attempt, or input paths.")


def run_wizard(session_path, input_path=None, context_path=None, output_path=None, input_fn=input, output_fn=print, repo=None, stack=None, component=None, guided=False):
    """Hold one cooperative session lock throughout the interactive lifecycle.

    A normally suspended session releases its lock. An abruptly terminated
    process may leave a lock; it must be inspected and removed manually after
    establishing that no wizard still uses this session. Lock age is no proof.
    """
    if guided:
        from .workflow import run_guided_workflow
        return run_guided_workflow(session_path, input_path, context_path, output_path, input_fn, output_fn, repo, stack, component)
    lock = None
    acquired = False
    try:
        session_path = _local_path(session_path)
        _validate_scopes(session_path, {"input": input_path, "context": context_path, "output": output_path})
        # Check restart scopes before creating the lock or any attempt records.
        # Saved state is checked again under the lock before it is consumed.
        saved = _session(session_path)
        combined = dict(saved["paths"])
        combined.update({name: value for name, value in (("input", input_path), ("context", context_path), ("output", output_path)) if value is not None})
        _validate_scopes(session_path, combined)
        lock = session_path.parent / (".intune-wizard-lock-" + hashlib.sha256(str(session_path).encode()).hexdigest()[:32])
        from .io import mkdir_durable, sync_directory
        mkdir_durable(lock.parent)
        try:
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise AppError("wizard_session_locked", "Another wizard or an interrupted session holds this session lock.") from None
        acquired = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps({"schema_version": "1.0.0", "session": str(session_path), "pid": os.getpid()}).encode())
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(lock.parent)
        return _run_wizard(session_path, input_path, context_path, output_path, input_fn, output_fn, repo, stack, component)
    except (AppError, OSError, ValueError) as error:
        output_fn("Cannot start session: " + _code(error))
        return {"status": "blocked", "error": _code(error), "session": str(session_path), "execution_authorized": False}
    finally:
        if acquired:
            try:
                lock.unlink(missing_ok=True)
                sync_directory(lock.parent)
            except OSError:
                return {"status": "blocked", "error": "wizard_lock_cleanup_not_durable", "session": str(session_path), "execution_authorized": False}


def _run_wizard(session_path, input_path=None, context_path=None, output_path=None, input_fn=input, output_fn=print, repo=None, stack=None, component=None):
    """Load restart hints and run the local controller under the caller's lock."""
    session_path = Path(session_path).absolute()
    output_fn("Intune IaC local wizard: synthetic bounded generation; unqualified production exports are review-only; supported plugin captures may emit inactive candidate text. No cloud, native, import or apply execution.")
    try:
        state = _session(session_path)
    except (AppError, OSError, ValueError) as error:
        output_fn("Cannot load session: " + _code(error))
        return {"status": "blocked", "error": _code(error), "session": str(session_path)}
    if (repo is not None or "repository" in state) and context_path is not None:
        output_fn("Repository mode creates its own target context; omit --context.")
        return {"status": "blocked", "error": "repository_context_conflict", "session": str(session_path), "execution_authorized": False}
    if repo is None and "repository" not in state and (stack is not None or component is not None):
        return {"status": "blocked", "error": "repository_required", "session": str(session_path), "execution_authorized": False}
    session = _WizardSession(session_path, state, input_fn, output_fn)
    session.configure(repo, stack, component, {"input": input_path, "context": context_path, "output": output_path})
    return session.run()


class _WizardSession:
    """One lock-held interaction with explicit state handlers and evidence checks.

    State remains an untrusted restart hint. Inspection and generated output are
    reconstructed before generation or handoff; no method executes cloud IaC.
    """

    def __init__(self, session_path, state, input_fn, output_fn):
        self.session_path = session_path
        self.state = state
        self.input_fn = input_fn
        self.output_fn = output_fn
        self.inspection = None
        self.attempt_dir = session_path.parent / "attempts"

    def configure(self, repo, stack, component, supplied):
        changed = self.configure_repository(repo, stack, component)
        for name, value in supplied.items():
            if value is not None:
                new_path = str(Path(value).absolute())
                if self.state["paths"].get(name) != new_path:
                    changed = True
                    self.state["paths"][name] = new_path
        if changed:
            self.state.update(step="inspect", fingerprints={}, generated=None, conflict_reason=None)
        self.route_missing_inputs()

    def configure_repository(self, repo, stack, component):
        changed = False
        if repo is not None:
            root = str(Path(repo).absolute())
            if self.state.get("repository", {}).get("root") != root:
                self.state["repository"] = {"root": root, "stack": None, "component": None, "selected_policy_id": None, "source_fingerprint": None}
                self.state["paths"].pop("context", None)
                changed = True
        if "repository" in self.state:
            for name, value in (("stack", stack), ("component", component)):
                if value is not None and self.state["repository"][name] != value:
                    self.state["repository"][name] = value
                    if name == "stack":
                        self.state["repository"]["component"] = None
                    changed = True
        return changed

    def route_missing_inputs(self):
        if "repository" in self.state:
            target = self.state["repository"]
            prerequisites = ((not target["stack"], "stack"), (not target["component"], "component"),
                             ("input" not in self.state["paths"], "source"), (not target["selected_policy_id"], "policy"),
                             ("output" not in self.state["paths"], "output"))
        else:
            prerequisites = ((name not in self.state["paths"], step) for name, step in (("input", "source"), ("context", "context"), ("output", "output")))
        for missing, step in prerequisites:
            if missing:
                self.state["step"] = step
                break
    def save(self):
        _validate_scopes(self.session_path, self.state['paths'])
        write_json(self.session_path, self.state)

    def finish(self, status):
        self.save()
        return {'status': status, 'step': self.state['step'], 'session': str(self.session_path), 'output': self.state['paths'].get('output'), 'generated': self.state['generated'] is not None, 'execution_authorized': False}

    def invalidate(self):
        self.inspection = None
        self.state.update(step='inspect', fingerprints={}, generated=None, conflict_reason=None)

    def repository_choices(self):
        from .repository import discover_repository
        discovery = discover_repository(self.state['repository']['root'])
        stacks = discovery.get('stacks', [])
        if discovery.get('status') == 'blocked':
            self.output_fn('Repository discovery contains blockers; only resolved literal targets are selectable.')
        blockers = list(discovery.get('blockers', []))
        blockers.extend((blocker for item in stacks for target in item.get('components', []) for blocker in target.get('blockers', [])))
        codes = {blocker.get('code') for blocker in blockers if isinstance(blocker, dict)}
        for code in sorted((code for code in codes if isinstance(code, str) and re.fullmatch('[a-z][a-z0-9_]{0,100}', code))):
            self.output_fn('  repository blocker: ' + code)
        return stacks

    def refresh_repository(self):
        if 'repository' not in self.state:
            return True
        try:
            expected = _repository_context(self.state['repository'], self.state['paths']['input'])
        except (AppError, OSError, ValueError):
            self.invalidate()
            raise
        try:
            current = load_json(self.state['paths']['context'])
        except (KeyError, AppError, OSError, ValueError):
            current = None
        fingerprint = expected['repository_source_fingerprint']
        if current != expected or self.state['repository']['source_fingerprint'] != fingerprint:
            had_context = 'context' in self.state['paths']
            self.state['paths']['context'] = _write_repository_context(self.session_path, expected)
            self.state['repository']['source_fingerprint'] = fingerprint
            self.invalidate()
            if had_context:
                self.output_fn('Repository or capture evidence changed; target context rebuilt and generated review invalidated.')
            return False
        return True

    def inspect(self):
        before = _fingerprints(self.state['paths'])
        parameters = {k: self.state['paths'][k] for k in ('input', 'context')}
        proposed = runner.preview('inspect', parameters, self.attempt_dir)
        if proposed.get('status') != 'ready':
            raise AppError('inspection_preview_rejected', 'Inspection preview was rejected.')
        self.inspection = _outcome(runner.run('inspect', parameters, self.attempt_dir))
        if 'repository' in self.state and self.inspection.get('source_mode') == 'synthetic':
            self.inspection = dict(self.inspection, status='blocked', blockers=[*self.inspection.get('blockers', []), {'code': 'syntheticcore_target_unqualified'}])
        after = _fingerprints(self.state['paths'])
        if before != after or self.inspection.get('source_sha256') != after['input'] or self.inspection.get('context_sha256') != after['context']:
            raise AppError('source_changed_during_inspection', 'Input changed during local inspection.')
        self.state['fingerprints'] = after

    def revalidate(self):
        _validate_scopes(self.session_path, self.state['paths'])
        if not self.refresh_repository():
            return False
        if self.state['fingerprints'] and _fingerprints(self.state['paths']) != self.state['fingerprints']:
            self.output_fn('Source or context bytes changed; selection and generated review invalidated. Reinspect before continuing.')
            self.invalidate()
            return False
        if self.state['step'] != 'conflict' and self.state['generated'] is not None:
            try:
                output_matches = _output_snapshot(self.state['paths']['output']) == self.state['generated']
            except (AppError, OSError, ValueError):
                output_matches = False
            if not output_matches:
                self.output_fn('Generated output or ownership manifest changed. Existing files will be preserved.')
                self.state.update(step='conflict', conflict_reason='output_changed')
                return False
        if self.state['step'] != 'conflict' and self.state['generated'] is not None:
            try:
                verified = engine.verify_project(self.state['paths']['input'], self.state['paths']['context'], self.state['paths']['output'])
                if verified.get('preservation_verified') is not True or verified.get('manifest_sha256') != self.state['generated']['manifest_sha256'] or verified.get('file_count') != self.state['generated']['file_count']:
                    raise AppError('postcondition_failed', 'Output differs from the source-derived project.')
            except (AppError, OSError, ValueError):
                self.output_fn('Saved output could not be verified against current source bytes. Existing files will be preserved.')
                self.state.update(step='conflict', conflict_reason='output_changed')
                return False
        return True

    def run(self):
        try:
            while True:
                step = self.state["step"]
                choices = self.prepare_choices(step)
                if step in {"inspect", "preview", "review", "conflict"} and not self.prepare_review(step):
                    continue
                step = self.state["step"]
                answer = self.input_fn(self.prompt(step)).strip()
                result = self.dispatch(step, answer, choices)
                if result is not None:
                    return result
        except (EOFError, KeyboardInterrupt):
            self.output_fn("Interrupted; session saved for resume.")
            try:
                return self.finish("suspended")
            except (AppError, OSError, ValueError) as error:
                return self.failure(error)
        except (AppError, OSError, ValueError) as error:
            self.output_fn("Session could not be saved: " + _code(error))
            return self.failure(error)

    def failure(self, error):
        return {"status": "blocked", "error": _code(error), "session": str(self.session_path)}

    def selectable_components(self, stack):
        return [item for item in stack.get("components", []) if item.get("selectable") is True and item.get("kind") == "terraform"]

    def selection_choices(self, step):
        if step == "policy":
            choices = sorted(_policy_ids(self.state["paths"]["input"]))
            self.output_fn("Observed policy UUIDs; display names do not determine selection:")
            return choices
        stacks = self.repository_choices()
        if step == "stack":
            self.output_fn("Physical stack manifests with resolved literal components:")
            return [item["stack"] for item in stacks if self.selectable_components(item)]
        selected = next((item for item in stacks if item["stack"] == self.state["repository"]["stack"]), {})
        self.output_fn("Resolved components in selected stack:")
        return [item["name"] for item in self.selectable_components(selected)]

    def prepare_choices(self, step):
        choices = []
        if step not in {"stack", "component", "policy"}:
            return choices
        try:
            choices = self.selection_choices(step)
            for index, choice in enumerate(choices[:100], 1):
                self.output_fn("  " + str(index) + ". " + choice)
            if not choices:
                self.output_fn("No selectable entries. Repair the local evidence, go back, or save.")
        except (AppError, OSError, ValueError) as error:
            self.output_fn("Local selection unavailable: " + _code(error))
        return choices

    def prepare_review(self, step):
        try:
            if not self.revalidate():
                self.save()
                return False
            # Every resume rebuilds inspection; saved summaries never grant readiness.
            if self.inspection is None:
                self.inspect()
            if step == "inspect":
                self.state["step"] = step = "preview"
            {"preview": self.display_preview, "review": self.display_review, "conflict": self.display_conflict}[step]()
            self.save()
        except (AppError, OSError, ValueError) as error:
            self.output_fn("Local inspection unavailable: " + _code(error) + ". Supply a complete local export/context, edit paths, or save.")
            self.inspection = None
            self.state["step"] = "preview"
        return True

    def display_preview(self):
        try:
            policy_id = str(UUID(self.inspection.get("policy_id")))
        except (ValueError, TypeError, AttributeError):
            policy_id = "unavailable"
        self.output_fn("Selected policy ID: " + policy_id)
        if "repository" in self.state:
            self.display_repository_target()
        policy_ids = sorted(_policy_ids(self.state["paths"]["input"]))
        self.output_fn("Observed policy UUIDs (up to 20 of " + str(len(policy_ids)) + "): " + ", ".join(policy_ids[:20]))
        self.display_mapping()

    def display_repository_target(self):
        context = load_json(self.state["paths"]["context"])
        self.output_fn("Repository target: " + context["stack"] + " / " + context["component"] + "; implementation: " + context["implementation"])
        self.output_fn("Tenant UUID: " + context["tenant_id"] + " (source-asserted by local capture; not authenticated). Authorization: emit_only.")

    def display_mapping(self):
        normalized = self.inspection.get("normalized", {})
        coverage = normalized.get("coverage", []) if isinstance(normalized, dict) else []
        blockers = self.inspection.get("blockers", [])
        mapping_status = "ready (synthetic, emit-only)" if self.inspection.get("status") == "ready" else "blocked; review-only"
        if self.inspection.get("source_mode") == "plugin_graph_capture" and normalized.get("candidate_mapping_complete") is True:
            mapping_status = "inactive candidate available; execution blocked"
        self.output_fn("Mapping: " + mapping_status + "; coverage records: " + str(len(coverage)) + "; blockers: " + str(len(blockers)))
        if self.inspection.get("source_mode") == "plugin_graph_capture":
            self.output_fn("Inactive candidate mapping: " + ("available" if normalized.get("candidate_mapping_complete") is True else "blocked") + "; repository ownership, provider qualification and execution remain unverified.")
        self.output_fn("Bounded mapping: settings catalog policy -> microsoft365_graph_beta_device_management_settings_catalog_configuration_policy_json. Referenced groups and filters remain externally owned.")
        for blocker in blockers:
            self.output_fn("  blocker: " + self.blocker_code(blocker))

    def blocker_code(self, blocker):
        code = blocker.get("code", "mapping_blocker") if isinstance(blocker, dict) else "mapping_blocker"
        return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,100}", code) else "mapping_blocker"

    def display_review(self):
        self.output_fn("Local generated proposal verified. Review README.md and generated-files.json; synthetic proposals include adoption/coverage.json, adoption/field-accounting.json and adoption/capability.json. Production capture reviews include BLOCKED.json and review/normalized.json. No tenant/provider qualification or execution approval is implied.")
        if self.inspection.get("source_mode") == "plugin_graph_capture":
            self.output_fn("Supported plugin captures may include inactive candidates/**/*.tf.txt for review. Candidate text is not executable IaC and does not establish ownership of the selected component.")

    def display_conflict(self):
        self.output_fn("File conflict: use new-path, review, or cancel. Existing output will not be overwritten.")

    def prompt(self, step):
        prompt = {
            "stack": "Stack selector or number [save/cancel]: ",
            "component": "Component selector or number [back/save/cancel]: ",
            "policy": "Policy UUID or number [back/save/cancel]: ",
            "source": "Local export path [save/cancel]: ",
            "context": "Bounded context JSON path [back/save/cancel]: ",
            "output": "Staging output directory [back/save/cancel]: ",
            "preview": "Preview [generate/review/select UUID/back/edit source|context|output/save/cancel]: ",
            "review": "Review [finish/back/edit source|context|output/save/cancel]: ",
            "conflict": "Conflict [new-path/review/back/save/cancel]: ",
        }[step]
        if step == "output" and "repository" in self.state:
            default = self.state["paths"].get("output", str(self.session_path.parent / "intune-proposal"))
            return "Staging output directory [default: " + default + "; back/save/cancel]: "
        if step in {"preview", "review"} and "repository" in self.state:
            return prompt.replace("edit source|context|output", "edit source|stack|component|policy|output")
        return prompt

    def dispatch(self, step, answer, choices):
        command, _, argument = answer.partition(" ")
        command = command.lower()
        common = {"save": self.handle_save, "cancel": self.handle_cancel, "back": self.handle_back, "edit": self.handle_edit}
        if command in common:
            return common[command](step, argument)
        if step in {"stack", "component", "policy"}:
            return self.handle_selection(step, answer, choices)
        if step in {"source", "context", "output"}:
            return self.handle_path(step, answer)
        if step == "conflict":
            return self.handle_conflict(command)
        commands = {("preview", "select"): self.handle_select, ("preview", "review"): self.handle_inspection_handoff,
                    ("review", "finish"): self.handle_generated_handoff, ("preview", "generate"): self.handle_generate}
        handler = commands.get((step, command))
        if handler is not None:
            return handler(argument)
        self.output_fn("Choose one of the commands shown in the prompt.")

    def handle_save(self, step, argument):
        self.output_fn("Session saved; resume with the same --session path.")
        return self.finish("suspended")

    def handle_cancel(self, step, argument):
        return self.finish("suspended" if step == "conflict" else "cancelled")

    def handle_back(self, step, argument):
        previous = {"stack": "stack", "component": "stack", "policy": "source", "source": "source", "context": "source", "output": "context", "preview": "output", "review": "preview", "conflict": "output"}
        if "repository" in self.state:
            previous.update(source="component", output="policy")
        self.state["step"] = previous[step]

    def handle_edit(self, step, argument):
        targets = {"source": "source", "context": "context", "output": "output"}
        if "repository" in self.state:
            targets.update(context="component", stack="stack", component="component", policy="policy")
        target = targets.get(argument.strip().lower())
        if target is None:
            self.output_fn("Use edit source, edit context, or edit output.")
        else:
            self.state["step"] = target

    def handle_selection(self, step, answer, choices):
        selection = answer
        if len(answer) <= 3 and answer.isdecimal() and 1 <= int(answer) <= min(100, len(choices)):
            selection = choices[int(answer) - 1]
        if selection not in choices:
            self.output_fn("Choose an observed selectable value or its displayed number.")
            return
        repository = self.state["repository"]
        self.invalidate()
        if step == "stack":
            repository.update(stack=selection, component=None)
            self.state["step"] = "component"
        elif step == "component":
            repository["component"] = selection
            self.state["step"] = "policy" if "input" in self.state["paths"] else "source"
        else:
            repository["selected_policy_id"] = selection
            if not self.select_repository_policy():
                return
        self.save()

    def select_repository_policy(self):
        try:
            self.refresh_repository()
        except (AppError, OSError, ValueError) as error:
            self.output_fn("Target context unavailable: " + _code(error))
            self.state["step"] = "policy"
            return False
        self.state["step"] = "inspect" if "output" in self.state["paths"] else "output"
        return True

    def handle_path(self, step, answer):
        name = {"source": "input", "context": "context", "output": "output"}[step]
        if not answer:
            if step == "output" and "repository" in self.state and name not in self.state["paths"]:
                self.state["paths"][name] = str(self.session_path.parent / "intune-proposal")
            if name not in self.state["paths"]:
                self.output_fn("A local path is required.")
                return
        else:
            self.state["paths"][name] = str(Path(answer).absolute())
            self.invalidate()
        self.state["step"] = {"source": "policy" if "repository" in self.state else "context", "context": "output", "output": "inspect"}[step]
        self.save()

    def handle_select(self, argument):
        try:
            if "repository" in self.state:
                self.select_observed_policy(argument)
            else:
                self.state["paths"]["context"] = _selected_context(self.session_path, self.state["paths"], argument.strip())
            self.invalidate()
            self.output_fn("Selection changed by UUID in a session-owned context copy. Reinspection required.")
        except (AppError, OSError, ValueError, TypeError) as error:
            self.output_fn("Selection rejected: " + _code(error))

    def select_observed_policy(self, argument):
        try:
            selected = str(UUID(argument.strip()))
        except (ValueError, AttributeError):
            raise AppError("invalid_policy_id", "Selection requires a policy UUID.") from None
        if selected not in _policy_ids(self.state["paths"]["input"]):
            raise AppError("policy_not_observed", "Selected policy was not observed.")
        self.state["repository"]["selected_policy_id"] = selected
        self.refresh_repository()

    def handle_conflict(self, command):
        if command == "new-path":
            self.state["step"] = "output"
        elif command == "review":
            self.output_fn("Conflict review: " + self.state["conflict_reason"] + ". Use a new staging directory or preserve these files and suspend.")
        else:
            self.output_fn("Choose new-path, review, back, save, or cancel.")

    def handle_inspection_handoff(self, argument):
        if self.inspection is None:
            self.output_fn("Inspection is unavailable; edit source/context or save before handoff.")
            return
        if not self.revalidate():
            return
        self.output_fn("Local inspection handoff complete; mapping blockers remain unresolved and no generated output is claimed.")
        return self.finish("review_only")

    def handle_generated_handoff(self, argument):
        if self.state["generated"] is None or set(self.state["fingerprints"]) != {"input", "context"}:
            self.invalidate()
            self.output_fn("Generated review evidence is missing; return to inspection before completion.")
            return
        if not self.revalidate():
            return
        self.output_fn("Local handoff complete. Cloud and native execution remain unavailable.")
        return self.finish("complete")

    def handle_generate(self, argument):
        if self.inspection is None:
            self.output_fn("Inspect a valid local source/context before generation.")
            return
        try:
            if not self.revalidate():
                return
            if "repository" in self.state and self.inspection.get("source_mode") == "synthetic":
                raise AppError("syntheticcore_target_unqualified", "The bounded synthetic generator does not qualify repository targets.")
            parameters = dict(self.state["paths"])
            self.preview_generation(parameters)
            self.output_fn("Generating a local proposal from the inspected bytes.")
            result = runner.run("generate", parameters, self.attempt_dir)
            if result.get("status") == "outcome_unknown":
                self.state.update(step="conflict", conflict_reason="outcome_unknown")
                self.save()
                return
            generated = _outcome(result)
            self.accept_generation(generated)
        except (AppError, OSError, ValueError) as error:
            code = _code(error)
            self.output_fn("Generation stopped: " + code)
            if code in {"output_conflict", "unsafe_output_path", "output_changed_after_generation"}:
                self.state.update(step="conflict", conflict_reason="output_conflict")
            self.save()

    def preview_generation(self, parameters):
        proposal = runner.preview("generate", parameters, self.attempt_dir)
        if proposal.get("status") != "ready":
            error = proposal.get("error", {})
            code = error.get("code", "generation_preview_rejected") if isinstance(error, dict) else "generation_preview_rejected"
            raise AppError(code, "Generation preview rejected.")

    def accept_generation(self, generated):
        if generated.get("preservation_verified") is not True:
            raise AppError("generation_not_verified", "Generation has no preservation proof.")
        if _fingerprints(self.state["paths"]) != self.state["fingerprints"]:
            self.invalidate()
            self.output_fn("Source/context changed during generation; reinspection required.")
            return
        if not self.refresh_repository():
            return
        snapshot = _output_snapshot(self.state["paths"]["output"])
        if snapshot is None or snapshot["manifest_sha256"] != generated.get("manifest_sha256"):
            raise AppError("output_changed_after_generation", "Generated output evidence changed.")
        self.state.update(step="review", generated=snapshot, conflict_reason=None)
        self.save()

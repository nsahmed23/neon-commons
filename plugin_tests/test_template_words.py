"""PKG-TEMPLATE-WORDS: no human text surface prints a command with an unresolved operand.

One renderer (readiness.placeholders_in_words, with command_in_words and commands_in) says such a command in words: every resolved
operand keeps its option and its value, every unresolved one keeps its option (or its position) and is described from the one
human operand-description table, readiness.TEMPLATE_WORDS. It reads three dialects, each from the product's own table: the shell
(the command line's parser), the workbench line terminal (its help table and command groups) and the wizard prompts (the journey's
and the workflow's answer words). The rendered-surface tests are the primary guard; the ast test is the introduction guard.
"""
import ast
import hashlib
import json
import re
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / 'intune_iac'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def said(text):
    from intune_iac import readiness
    return readiness.placeholders_in_words(text)


def unresolved(text):
    """The operands of the commands a printed text still holds that are placeholders, read in every dialect."""
    from intune_iac import entry, readiness
    return [operand for operand in readiness.command_operands(text) if entry.is_fill_in(operand)]


class VocabularyTests(unittest.TestCase):
    def test_the_description_table_and_the_shared_set_agree(self):
        from intune_iac import entry, readiness
        self.assertEqual(sorted(set(entry.FILL_IN_TEMPLATES) ^ set(readiness.TEMPLATE_WORDS)), [])
        for name in ('FILE', 'COMMIT', 'NAME', 'OBJECT_ID', 'DIGEST', 'NEW_OPERATION_DIR', 'DESIRED_JSON', 'OPERATION_DIR',
                     'REVISION', 'RESOLUTION_SHA256', 'STAGE', 'VALUE'):
            self.assertIn(name, readiness.TEMPLATE_WORDS)

    def test_the_dialects_come_from_the_products_own_tables(self):
        from intune_iac import cli, readiness
        shell, typed = readiness.dialects()
        self.assertTrue({'start', 'catalog', 'signin', 'workbench', 'repository'} <= set(shell))
        self.assertTrue({'init', 'companion', 'execute', 'diagnostics', 'repository-import'} <= set(shell['workbench']))
        self.assertTrue({'propose-from-intent', 'reconcile', 'repository-refresh', 'repository-entry', 'back', 'edit'} <= typed)
        self.assertEqual(set(shell), set(cli.parser()._subparsers._group_actions[0].choices))

    def test_the_wizard_words_are_the_ones_the_prompts_accept(self):
        from intune_iac import journey, workflow
        for module, prompt in ((journey, "'Journey [' + ('handoff/' if edits else '') + 'continue/UUIDs/"),
                               (workflow, "'Guided ' + step + ' [' + ('handoff/' if edits else '') + 'UUIDs/continue/")):
            text = (PACKAGE / (module.__name__.split('.')[-1] + '.py')).read_text(encoding='utf-8')
            self.assertIn(prompt, text)
            line = text[text.index(prompt):].split('\n')[0]
            offered = set(re.findall(r'[a-z]+', re.sub(r'UUIDs|RING|FIELD|STAGE|VALUE', ' ', line.split("']:")[0])))
            for word in module.ANSWER_COMMANDS:
                self.assertIn(word, offered, (module.__name__, word))


class RendererTests(unittest.TestCase):
    def test_a_resolved_operand_keeps_its_option_and_value_an_unresolved_one_its_option_and_description(self):
        self.assertEqual(said('Run: intune-iac capture --tenant 1111 --policy POLICY --output NEW_DIR --token-env TOKEN_VARIABLE_NAME'),
                         'Run: the capture command using --tenant 1111, naming --policy as the policy id (a GUID), --output as a new '
                         'folder for the output and --token-env as the name of the environment variable that holds the token')
        self.assertEqual(said("workbench repository-import --root STORE --repo REPOSITORY --stack orgs/reference/dev --revision COMMIT "
                              "--resource-address 'x.policy[\"k\"]'"),
                         "The workbench repository-import command using --stack orgs/reference/dev, --resource-address 'x.policy[\"k\"]', "
                         'naming --root as your store folder, --repo as your repository folder and --revision as the Git commit that '
                         'holds the edited project')

    def test_a_typed_command_is_read_with_or_without_the_colon_and_after_a_lead_word(self):
        self.assertEqual(said('Command:\n  propose-from-intent NEW_OPERATION_DIR'),
                         'Command:\n  the propose-from-intent command, naming a new folder for the operation')
        self.assertEqual(said('Use :reconcile OPERATION_DIR for explicit readback.'),
                         'Use the :reconcile command, naming the operation folder, for explicit readback.')
        self.assertEqual(said('or back STAGE, or edit to change course.'),
                         'or the back command, naming the stage to go back to, or edit to change course.')
        self.assertEqual(said('or edit output VALUE for a fresh staging directory.'),
                         'or the edit output command, naming the value to set, for a fresh staging directory.')

    def test_the_sign_in_rerun_names_the_account_and_the_folder(self):
        from intune_iac import signin
        text = said(signin.rerun_command('11111111-1111-4111-8111-111111111111', 'P', True))
        self.assertEqual(unresolved(text), [])
        self.assertIn('--tenant 11111111-1111-4111-8111-111111111111', text)
        self.assertIn('--output as a new folder for the output', text)
        self.assertIn('--account as the name of the account you signed in with', text)
        self.assertNotIn('--account as', said(signin.rerun_command('T', 'P', False)))

    def test_an_option_and_its_placeholder_outside_a_command_is_described_too(self):
        self.assertEqual(said('with --serve instead of --out FILE it serves'),
                         'with --serve instead of --out (the file to write the page to) it serves')

    def test_resolved_commands_and_plain_prose_are_unchanged(self):
        for text in ("Run: intune-iac workbench workspace --root 'estate dir/store'", 'No action needed.',
                     'Run: intune-iac doctor and pass its result.', 'Use :reconcile when an outcome is unknown.',
                     'intune-iac workbench execute --operation /ops/one --approve-digest ' + 'a' * 64):
            self.assertEqual(said(text), text)


class RenderedSurfaceTests(unittest.TestCase):
    """The primary guard: the human text a person sees, after all formatting and concatenation."""

    def test_the_sign_in_collect_text_view_with_and_without_account(self):
        from intune_iac import signin, signin_facts
        for account in (True, False):
            result = {'status': 'failed', 'error_code': 'collector_failed', 'collector_started': True, 'child_exit': 1, 'result': {}}
            lines = signin_facts.collect_lines(result, 100, 1, {'rerun': signin.rerun_command('T', 'P', account), 'output': '/x/out'})
            text = ' '.join(' '.join(lines).split())
            self.assertEqual(unresolved(' '.join(lines)), [], account)
            self.assertIn('To collect again, run: the signin collect command using --tenant T, --policy P, naming --output as a new '
                          'folder for the output', text)
            self.assertEqual('--account as the name of the account you signed in with' in text, account)

    def test_the_output_edit_next_steps_with_and_without_an_object_id(self):
        from intune_iac import output_edit
        for object_id, expected in (('abc', '--object abc'), (None, '--object as the exact object id of the policy')):
            text = said(output_edit._next_steps('key', object_id)[1])
            self.assertEqual(unresolved(text), [], object_id)
            self.assertIn(expected, text)
            self.assertIn('--root as your store folder', text)
            self.assertIn('--repo as your repository folder', text)
            self.assertIn('--revision as the Git commit that holds the edited project', text)
            self.assertIn('--stack orgs/reference/dev', text)                    # a resolved value is kept as printed

    def test_the_journey_the_workflow_and_the_wizard_print_the_next_steps_through_the_renderer(self):
        for module, needle in (('journey.py', "output_fn('Next: ' + placeholders_in_words(line))"),
                               ('workflow.py', "output_fn('Next: ' + placeholders_in_words(line))"),
                               ('wizard.py', 'self.output_fn("Next: " + placeholders_in_words(step))')):
            self.assertIn(needle, (PACKAGE / module).read_text(encoding='utf-8'), module)
        self.assertEqual(unresolved(said('Enter handoff to end this journey in the repository workflow, or back STAGE, or edit to '
                                         'change course.')), [])
        self.assertEqual(unresolved(said('Enter handoff to end this session in the repository workflow, or edit output VALUE for a '
                                         'fresh staging directory.')), [])

    def test_the_companion_actions_and_page(self):
        from intune_iac import companion_page, workbench, workbench_screens
        for command in (companion_page.COMPANION_WRITE, companion_page.COMPANION_SERVE):
            text = said(command)
            self.assertEqual(unresolved(text), [])
            self.assertIn('--root as your store folder', text)
            self.assertIn('--object as the exact object id of the policy', text)
        text = said(workbench.ACTION_EFFECTS['companion'])
        self.assertEqual(unresolved(text), [])
        self.assertNotIn('--out FILE', text)
        self.assertIn('--out as the file to write the page to', text)
        source = (PACKAGE / 'companion_page.py').read_text(encoding='utf-8')
        self.assertIn('status = placeholders_in_words(status)', source)
        screens = (PACKAGE / 'workbench_screens.py').read_text(encoding='utf-8')
        self.assertIn("placeholders_in_words(str(described))", screens)

    def test_the_execute_forms_say_the_digest_in_words(self):
        from intune_iac import workbench_screens
        text = workbench_screens._execute_forms('/ops/one')
        self.assertEqual(unresolved(text), [])
        self.assertIn('using /ops/one, naming the digest that the review shows', text)
        self.assertIn('--operation /ops/one, naming --approve-digest as the digest that the review shows', text)

    def test_the_diagnostics_interrupted_line_and_the_reconcile_recovery(self):
        self.assertEqual(unresolved(said('  intune-iac workbench diagnostics --root /s --object ID')), [])
        self.assertEqual(unresolved(said('Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.')),
                         [])
        for module, needle in (('workbench.py', "placeholders_in_words(\n                    '  intune-iac workbench diagnostics --root %s --object ID'"),
                               ('workbench_tui.py', "'recovery': __import__('intune_iac.readiness'")):
            self.assertIn(needle, (PACKAGE / module).read_text(encoding='utf-8'), module)


# -- the introduction guard ---------------------------------------------------------------------------------------------------

# Genuine usage synopses: the :help listing of the line terminal and the command-syntax part of the help legend. Allowed where the
# screen says that words in capitals stand for values the person supplies; SYNOPSIS_CONVENTION is that sentence.
SYNOPSIS = {
    ('workbench.py', 'companion FILE | serve | stop'), ('workbench.py', 'repository-entry REPOSITORY (the policies'),
    ('workbench.py', 'repository-refresh REVISION [RESOLUTION_SHA256]'), ('workbench.py', 'propose-from-intent NEW_OPERATION_DIR (selected'),
    ('workbench.py', 'propose DESIRED_JSON OUTPUT_DIR [CONTEXT_JSON]'), ('workbench.py', 'review OPERATION_DIR'),
    ('workbench.py', 'delivery OPERATION_DIR (read-only'), ('workbench.py', 'execute OPERATION_DIR EXPLICIT_REVIEW_DIGEST'),
    ('workbench.py', 'reconcile OPERATION_DIR'), ('workbench.py', 'deployment-record OPERATION_DIR INTENT_ID'),
    ('workbench_screens.py', ":workflow draws the selected policy's change path"),
    ('workbench_screens.py', 'propose DESIRED_JSON NEW_OPERATION_DIR or propose-from-intent'),
}
SYNOPSIS_CONVENTION = 'words in capitals stand for values you supply'

# Rendered at the human-text boundary by the renderer, each with a test above: the recorded text stays as it is for the JSON forms.
RENDERED = {
    ('companion_page.py', 'intune-iac workbench companion --root STORE --object ID --out FILE'),
    ('companion_page.py', 'intune-iac workbench companion --root STORE --object ID --serve'),
    ('output_edit.py', 'Copy the edited project into the repository you maintain and commit it'),
    ('signin.py', 'intune-iac signin collect --tenant %s --policy %s --output NEW_DIR (a '),
    ('workbench.py', '  intune-iac workbench diagnostics --root %s --object ID'),
    ('workbench_screens.py', '  intune-iac workbench execute --operation %s --approve-digest DIGEST'),
    ('workbench_screens.py', '  execute %s DIGEST'),
    ('workbench_screens.py', 'intune-iac workbench workflow --root ROOT --policy ID'),   # WORKFLOW_COMMAND: workflow_command_rows writes it
    ('workbench_tui.py', 'Use :reconcile OPERATION_DIR for explicit independent readback; never '),
    ('journey.py', 'Enter handoff to end this journey in the repository workflow, or back '),
    ('workflow.py', 'Enter handoff to end this session in the repository workflow, or edit '),
}

# NOT CLOSED in this package (reported): prompts and hints whose text also reaches JSON or whose display path was not found in time.
OPEN = {
    ('journey.py', 'Preserved prior artifacts. Restore the original evidence, or use edit '),
    ('journey.py', 'Completed; inspect evidence, back STAGE, edit, or save.'),
    ('repository_entry.py', 'commit the change, then repository-refresh COMMIT records it'),
    ('repository_entry.py', 'The key encodes tenant %s; this store holds tenant %s. Record it into '),
    ('workbench.py', ' Command:\n  propose-from-intent NEW_OPERATION_DIR'), ('workbench.py', ' Command:\n  propose DESIRED_JSON NEW_OPERATION_DIR'),
    ('workbench.py', 'To see how to record where this policy is maintained, run:\n  repository-entry RE'),
    ('workbench_diagnostics.py', 'In the line terminal or the CLI, where 9 and a are not keys, type repo'),
    ('workbench_diagnostics.py', 'Keep one repository as the source of this policy; choosing between rec'),
    ('workbench_repository.py', 'The repository still matches this intent. propose-from-intent NEW_OPER'),
    ('workbench_repository.py', 'The repository changed since this intent was recorded. Review the diff'),
    ('workbench_screens.py', 'none recorded; repository-entry REPOSITORY finds where this policy is '),
    ('workbench_screens.py', '  :repository-entry REPOSITORY'), ('workbench_screens.py', '    :queue-amend FILE %s'),
    ('workbench_tui.py', 'No active operation: review one first (5, or :review OPERATION_DIR).'),
}


class IntroductionGuardTests(unittest.TestCase):
    """Secondary guard: a string constant that holds a command with a placeholder operand must be named above. A constant alone does
    not prove a screen is clean (a run-time operand is added after it), which is why the rendered tests come first."""

    @staticmethod
    def flagged():
        from intune_iac import entry, readiness
        found = []
        for path in sorted(PACKAGE.glob('*.py')):
            if path.name in ('readiness.py', 'entry.py', 'catalog.py'):
                continue          # their recorded steps go through the same renderer; entry and catalog are covered by test_start_standin
            tree = ast.parse(path.read_text(encoding='utf-8'))
            docs = {id(n.body[0].value) for n in ast.walk(tree)
                    if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                    text = re.sub(r'(--[a-z-]+ )?%s', lambda m: (m.group(1) + 'value') if m.group(1) else 'intune-iac', node.value)
                    if any(entry.is_fill_in(operand) for operand in readiness.command_operands(text)):
                        found.append((path.name, node.value))
        return found

    def test_every_constant_with_a_placeholder_operand_is_named_and_none_is_new(self):
        known = SYNOPSIS | RENDERED | OPEN
        found = self.flagged()
        unnamed = [item for item in found if not any(item[0] == f and item[1].startswith(k) for f, k in known)]
        self.assertEqual([(f, v[:80]) for f, v in unnamed], [], 'a command with a placeholder operand that no test names')
        stale = sorted(item for item in known if not any(item[0] == f and v.startswith(item[1]) for f, v in found))
        self.assertEqual(stale, [], 'named, but no longer a constant with a placeholder operand: remove it from the list')

    def test_the_synopsis_allowlist_is_only_the_help_listing_and_the_help_legend(self):
        self.assertEqual({f for f, _ in SYNOPSIS}, {'workbench.py', 'workbench_screens.py'})
        self.assertTrue(all(k.startswith(('companion', 'repository-', 'propose', 'review', 'delivery', 'execute', 'reconcile',
                                          'deployment-record', ':workflow')) for _, k in SYNOPSIS))


# -- the JSON forms stay -----------------------------------------------------------------------------------------------------

PINS = {
    'companion commands': 'f9a85f432a92648a',
    'output_edit.next_steps with object': 'e29d33e98d156dc5',
    'output_edit.next_steps without object': 'b05e2e511470e9e2',
    'signin.rerun_command account': '8fc8c409d9e07a81',
    'signin.rerun_command no account': '0ee65af5f5d607f7',
    'workbench.ACTION_EFFECTS': '6ca05869dad7a6bd',
    'workbench.HELP': 'e6773881b7fbcfea',
}


class RecordedTextPinsTests(unittest.TestCase):
    """The recorded text that feeds the JSON forms (taken on fa3f022): the renderer is applied where a person reads, never here.
    The digests of `start --json` and `catalog --json` are pinned by test_start_standin (JSON_GOLDEN)."""

    def test_the_recorded_texts_are_byte_for_byte_what_they_were(self):
        from intune_iac import companion_page, output_edit, signin, workbench
        now = {
            'output_edit.next_steps with object': digest(output_edit._next_steps('k', 'abc')),
            'output_edit.next_steps without object': digest(output_edit._next_steps('k', None)),
            'signin.rerun_command account': digest(signin.rerun_command('T', 'P', True)),
            'signin.rerun_command no account': digest(signin.rerun_command('T', 'P', False)),
            'companion commands': digest([companion_page.COMPANION_WRITE, companion_page.COMPANION_SERVE]),
            'workbench.ACTION_EFFECTS': digest(workbench.ACTION_EFFECTS),
            'workbench.HELP': digest(workbench.HELP),
        }
        self.assertEqual(now, PINS)


if __name__ == '__main__':
    unittest.main()

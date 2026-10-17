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
import os
import re
import tempfile
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
                         'with --serve instead of --out (the file you name) it serves')

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
        self.assertIn('--out as the file you name', text)
        source = (PACKAGE / 'companion_page.py').read_text(encoding='utf-8')
        self.assertIn('status = placeholders_in_words(status)', source)
        screens = (PACKAGE / 'workbench_screens.py').read_text(encoding='utf-8')
        self.assertIn("placeholders_in_words(str(described))", screens)

    def test_the_execute_forms_say_the_digest_in_words(self):
        from intune_iac import workbench_screens
        text = said(workbench_screens._execute_forms('/ops/one'))      # the forms are recorded text; the screens say them in words
        self.assertEqual(unresolved(text), [])
        self.assertIn('using /ops/one, naming the digest that the review shows', text)
        self.assertIn('--operation /ops/one, naming --approve-digest as the digest that the review shows', text)

    def test_the_diagnostics_interrupted_line_and_the_reconcile_recovery(self):
        self.assertEqual(unresolved(said('  intune-iac workbench diagnostics --root /s --object ID')), [])
        self.assertEqual(unresolved(said('Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.')),
                         [])
        for module, needle in (('workbench.py', "placeholders_in_words(\n                    '  intune-iac workbench diagnostics --root %s --object ID'"),):
            self.assertIn(needle, (PACKAGE / module).read_text(encoding='utf-8'), module)


# -- the introduction guard ---------------------------------------------------------------------------------------------------

# Genuine usage synopses: derived exactly from the two help tables, never listed here by prefix. The permitted set is the string
# constants of workbench.HELP (the :help listing of the line terminal) and the command-syntax entries of workbench_screens.HELP_WORDS
# (the help legend). A constant that merely starts like one of them is not a synopsis.
def synopsis_constants():
    """{(file, exact constant)} of the permitted synopses, read from the source of the two tables with ast."""
    from intune_iac import entry, readiness
    found = set()
    tree = ast.parse((PACKAGE / 'workbench.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'HELP' for target in node.targets):
            found |= {('workbench.py', leaf.value) for leaf in ast.walk(node.value) if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str)}
    tree = ast.parse((PACKAGE / 'workbench_screens.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'HELP_WORDS' for target in node.targets):
            for entry_node in ast.walk(node.value):
                if isinstance(entry_node, ast.Tuple) and len(entry_node.elts) == 2 and all(isinstance(e, ast.Constant) for e in entry_node.elts):
                    text = entry_node.elts[1].value
                    if any(entry.is_fill_in(operand) for operand in readiness.command_operands(text)):
                        found.add(('workbench_screens.py', text))
    return found


SYNOPSIS_CONVENTION = 'words in capitals stand for values you supply'      # the help legend's sentence contains it

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

# Nothing is open: every constant that holds a command with a placeholder operand is a synopsis, rendered at the boundary where it is
# displayed (a rendered test below), or not a command a person reads at all (named). The list is asserted empty.
OPEN = set()

# Rendered where the screens display them (workbench_screens.step_rows and _labelled_steps render a whole step; the others render the
# string where it is built), each exercised in RenderedEverywhereTests.
RENDERED |= {
    ('repository_entry.py', 'commit the change, then repository-refresh COMMIT records it'),
    ('repository_entry.py', 'The key encodes tenant %s; this store holds tenant %s. Record it into '),
    ('workbench.py', ' Command:\n  propose-from-intent NEW_OPERATION_DIR'), ('workbench.py', ' Command:\n  propose DESIRED_JSON NEW_OPERATION_DIR'),
    ('workbench.py', 'To see how to record where this policy is maintained, run:\n  repository-entry RE'),
    ('workbench_diagnostics.py', 'In the line terminal or the CLI, where 9 and a are not keys, type repo'),
    ('workbench_diagnostics.py', 'Keep one repository as the source of this policy; choosing between rec'),
    ('workbench_repository.py', 'The repository still matches this intent. propose-from-intent NEW_OPER'),
    ('workbench_repository.py', 'The repository changed since this intent was recorded. Review the diff'),
    ('workbench_screens.py', 'none recorded; repository-entry REPOSITORY finds where this policy is '),
    ('workbench_delivery.py', 'Review the change (5); the digest is the one on the review'),
    # the sign-in steps: printed on the start screen and the catalog through the goal rows, rendered by CheckSigninScreenTests
    ('signin_facts.py', 'az account set --subscription SUBSCRIPTION'), ('signin_facts.py', 'az logout --username NAME'),
    ('signin_facts.py', 'Make one active with: gh auth switch --user NAME'),
    ('workbench_screens.py', ':repository-entry REPOSITORY'), ('workbench_screens.py', '    :queue-review-template %s NEW_JSON'),
    ('workbench_screens.py', '  :queue-review-template %s NEW_JSON'), ('workbench_screens.py', '    :queue-amend FILE %s'),
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
        known = RENDERED | OPEN
        permitted = synopsis_constants()
        found = self.flagged()
        unnamed = [item for item in found if item not in permitted
                   and not any(item[0] == f and item[1].startswith(k) for f, k in known)]
        self.assertEqual([(f, v[:80]) for f, v in unnamed], [], 'a command with a placeholder operand that no test names')
        stale = sorted(item for item in known if not any(item[0] == f and v.startswith(item[1]) for f, v in found))
        self.assertEqual(stale, [], 'named, but no longer a constant with a placeholder operand: remove it from the list')

    def test_nothing_is_open(self):
        self.assertEqual(OPEN, set())

    def test_the_synopsis_allowlist_is_exact_and_comes_from_the_two_help_tables(self):
        permitted = synopsis_constants()
        self.assertTrue({f for f, _ in permitted} == {'workbench.py', 'workbench_screens.py'})
        self.assertGreater(len(permitted), 50)
        found = set(self.flagged())
        # the help tables' own synopses are all there, exactly
        self.assertTrue({item for item in found if item[0] == 'workbench.py' and item in permitted})
        # a new constant that only starts like a synopsis is not one
        self.assertNotIn(('workbench.py', 'review OPERATION_DIR immediately'), permitted)
        self.assertNotIn(('workbench.py', 'review OPERATION_DIR (read-only) and more'), permitted)

    def test_every_permitted_synopsis_is_shown_on_a_page_that_also_shows_the_convention(self):
        from intune_iac import workbench, workbench_screens
        pages = [' '.join(' '.join(workbench_screens.details_lines(workbench.HELP, 100, synopsis=True)).split()),
                 ' '.join(' '.join(workbench_screens.help_lines(100)).split())]
        shown = 0
        for file, text in sorted(synopsis_constants()):
            wanted = ' '.join(text.split())
            holders = [page for page in pages if wanted in page]
            if not holders:
                continue                     # a constant of HELP that is not a command syntax entry (a heading, a sentence): not shown as one
            shown += 1
            for page in holders:
                with self.subTest(synopsis=wanted[:60]):
                    self.assertIn(workbench_screens.SYNOPSIS_CONVENTION, page)
        self.assertGreater(shown, 50)


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



# -- end to end: the human text each site really prints ------------------------------------------------------------------------

class RenderedEverywhereTests(unittest.TestCase):
    def test_the_help_legend_says_what_capitals_mean(self):
        from intune_iac import workbench_screens
        text = ' '.join(' '.join(workbench_screens.help_lines(100)).split())
        self.assertIn(SYNOPSIS_CONVENTION, text)
        self.assertIn(workbench_screens.SYNOPSIS_CONVENTION, text)
        self.assertIn('propose DESIRED_JSON NEW_OPERATION_DIR', text)       # the allowlisted synopsis is there, with its convention

    def test_the_journey_and_the_guided_workflow_print_words_in_their_messages_and_prompts(self):
        import tempfile
        from plugin_tests import test_journey_completion as tj, test_workflow as tw
        # journey
        case = tj.JourneyCompletionTests('test_contract_is_closed_and_executable')
        case.setUp()
        try:
            case.complete()
            case.edit_policy_description()
            prompts = []
            queue = iter(['handoff'])

            def read(prompt):
                prompts.append(prompt)
                value = next(queue, None)
                if value is None:
                    raise EOFError()
                return value
            case.api().run_journey(case.session, input_fn=read, output_fn=case.messages.append)
            messages = '\n'.join(case.messages)
            for text in (messages, '\n'.join(prompts)):
                self.assertEqual(unresolved(text), [], text)
            self.assertIn('--revision as the Git commit that holds the edited project', messages)
            self.assertIn('--root as your store folder', messages)
            self.assertTrue(any('back (then a stage)' in prompt for prompt in prompts), prompts)
        finally:
            case.doCleanups()
        # guided workflow
        case = tw.WorkflowTests('test_guided_entrypoint_reaches_real_generated_handoff')
        case.setUp()
        try:
            case.run_flow([tw.POLICY, 'generate', 'finish'])
            case.edit_policy_description()
            case.messages.clear()
            del case.prompts[:]
            case.run_flow(['handoff'], supplied=False)
            messages = '\n'.join(case.messages)
            for text in (messages, '\n'.join(case.prompts)):
                self.assertEqual(unresolved(text), [], text)
            self.assertIn('the edit output command, naming the value to set', ' '.join(messages.split()))
            self.assertIn('--revision as the Git commit that holds the edited project', messages)
            self.assertTrue(any('cohort (then a ring and UUIDs)' in prompt for prompt in case.prompts), case.prompts)
        finally:
            case.doCleanups()

    def test_the_companion_page_status_is_words(self):
        from plugin_tests import test_companion_page as tc
        tc.StructureTests.setUpClass()
        case = tc.StructureTests('test_a_static_page_says_plainly_that_it_does_not_update_itself')
        try:
            status = tc.section(case.page(), 'live')
            self.assertEqual(unresolved(status), [], status)
            self.assertIn('--object as the exact object id of the policy', status)
            self.assertIn('--out', status)
            self.assertNotIn('--out FILE', status)
        finally:
            tc.StructureTests.tearDownClass()

    def test_the_actions_screen_describes_the_companion_in_words(self):
        from intune_iac import workbench, workbench_screens
        action = {'label': 'Write the companion page', 'available': True, 'effects': workbench.ACTION_EFFECTS['companion'],
                  'summary': 'x', 'command': 'companion'}
        text = ' '.join(' '.join(workbench_screens.actions_lines([action], 0, 100, 'P', 'o' * 8 + '-1111-4111-8111-' + '1' * 12)).split())
        self.assertEqual(unresolved(text), [], text)
        self.assertIn('--out as the file you name', text)

    def test_the_other_tenant_explanation_and_the_repository_next_actions_are_words(self):
        from intune_iac import workbench_diagnostics, workbench_repository, workbench_screens
        explanation = ('The key encodes tenant T1; this store holds tenant T2. Record it into a store for that tenant '
                       '(workbench init --root STORE --tenant T1).')
        value = {'repository': '/work/repository', 'revision': 'c' * 40, 'tenant_id': 'T2', 'status': 'discovered',
                 'components': [], 'next_action': 'One policy.', 'candidates': [{
                     'number': 1, 'stack': 's', 'component': 'c', 'policy_key': 'p_a', 'object_id': '2' * 8 + '-2222-4222-8222-' + '2' * 12,
                     'observed': {'present': False}, 'state': 'other_tenant', 'backend': 'local', 'backend_source': 'none_declared',
                     'resource_address': None, 'explanation': explanation}]}
        text = ' '.join(' '.join(workbench_screens.repository_entry_lines(value, 100)).split())
        self.assertEqual(unresolved(text), [], text)
        self.assertIn('--root as your store folder', text)
        self.assertIn('--tenant T1', text)
        for step in (workbench_repository.NEXT_ACTIONS['current'], workbench_repository.NEXT_ACTIONS['stale'],
                     workbench_diagnostics.LINE_COMMAND):
            rows = ' '.join(' '.join(workbench_screens.step_rows(step, 100)).split())
            self.assertEqual(unresolved(rows), [], rows)
        rows = ' '.join(workbench_screens._labelled_steps('Next', workbench_diagnostics.LINE_COMMAND, 100, 10))
        self.assertIn('the repository-refresh command, naming the Git revision to record', ' '.join(rows.split()))

    def test_the_inspector_next_actions_and_the_interrupted_diagnostics_line_are_words(self):
        from intune_iac import workbench, workbench_screens
        steps = workbench._next_actions({'selected_repository': {'artifact_id': 'a'}}, {'signals': [], 'status': 'ok'}, True)
        steps += workbench._next_actions({}, {'signals': [], 'status': 'ok'}, True)
        rows = ' '.join(' '.join(workbench_screens._labelled_steps('  ', step['step'], 100, 2)) for step in steps)
        self.assertEqual(unresolved(rows), [], rows)
        self.assertIn('propose-from-intent command, naming a new folder for the operation', rows)
        self.assertIn('propose command, naming your desired-policy JSON file and a new folder for the operation', rows)
        lines = workbench.interrupted_lines({'store_root': '/s', 'during': {'command': 'other'}, 'interrupted': True})
        self.assertEqual(unresolved('\n'.join(map(str, lines))), [], lines)

    def test_the_reconcile_recovery_and_the_review_notice_are_words(self):
        for module, needle in (('workbench_tui.py', "placeholders_in_words('No active operation: review one first (5, or :review OPERATION_DIR).')"),
                               ('workbench_screens.py', "placeholders_in_words('    :queue-amend FILE %s' % prior)"),
                               ('workbench_screens.py', "placeholders_in_words(':repository-entry REPOSITORY')"),
                               ('workbench_screens.py', "placeholders_in_words('none recorded; repository-entry REPOSITORY finds")):
            source = ' '.join((PACKAGE / module).read_text(encoding='utf-8').split())
            self.assertIn(' '.join(needle.split()), source, (module, needle))
        for text in (':queue-amend FILE x', ':repository-entry REPOSITORY', 'No active operation: review one first (5, or :review OPERATION_DIR).',
                     'none recorded; repository-entry REPOSITORY finds where this policy is maintained'):
            self.assertEqual(unresolved(said(text)), [], text)


# -- the JSON forms of repository-entry and output classify -------------------------------------------------------------------

# digests of the JSON forms of `workbench repository-entry` and of the generated-output classification, taken on fa3f022 (the temporary
# directories are masked): the renderer never touches a recorded text.
JSON_PINS = {
    'output classify edited': '4811257a0e921d26',
    'output classify unchanged': '07caae44eeae0c63',
    'repository entry': '0f184a802cf1d72c',
}


def _digest(value, *masks):
    text = json.dumps(value, sort_keys=True)
    for mask in masks:
        text = text.replace(str(mask), 'MASK')
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class JsonPinsTests(unittest.TestCase):
    def test_the_json_of_repository_entry_and_output_classify_is_what_it_was(self):
        found = {}
        from plugin_tests import test_output_edit as o
        case = o.OutputEditTests('test_unchanged_output_is_unchanged')
        case.setUp()
        try:
            found['output classify unchanged'] = _digest(case.classify(), case.root)
            case.stack.write_text(case.stack.read_text().replace(o.OBSERVED, o.EDITED))
            found['output classify edited'] = _digest(case.classify(), case.root)
        finally:
            case.doCleanups()
        from plugin_tests import test_repository_entry as r
        case = r.RepositoryEntryTests('test_a_generated_repository_offers_its_policy_with_every_value_derived')
        case.setUp()
        try:
            r.commit(case.repo)
            found['repository entry'] = _digest(case.survey(), case.repo, case.store.root if hasattr(case.store, 'root') else '',
                                                Path(str(case.repo)).parent)
        finally:
            case.doCleanups()
        self.assertEqual(found, JSON_PINS)



# -- round 3: the layers, read as a person reads them -------------------------------------------------------------------------

class LayerTests(unittest.TestCase):
    def test_the_typed_details_layer_renders_every_string_it_prints(self):
        from intune_iac import workbench, workbench_diagnostics, workbench_screens
        value = {'effects': workbench.ACTION_EFFECTS['companion'], 'recovery': 'Use :reconcile OPERATION_DIR for readback.',
                 'steps': ['Command:\n  propose-from-intent NEW_OPERATION_DIR', 'propose DESIRED_JSON NEW_OPERATION_DIR'],
                 'line': workbench_diagnostics.LINE_COMMAND, 'plain': 'nothing to say', 'number': 3}
        text = '\n'.join(workbench_screens.details_lines(value, 100))
        self.assertEqual(unresolved(text), [], text)
        flat = ' '.join(text.split()).lower()
        self.assertIn('--object as the exact object id of the policy', flat)
        self.assertIn('the propose command, naming your desired-policy json file and a new folder for the operation', flat)
        self.assertIn('the repository-refresh command, naming the git revision to record', flat)
        self.assertIn('nothing to say', flat)

    def test_the_actions_layer_renders_the_command_row_of_an_action(self):
        from intune_iac import workbench_screens
        for command, needs, expected in (('companion ', ['FILE: where to write it'], 'companion command, naming the file you name'),
                                         ('propose  /ops/new', ['DESIRED_JSON: the desired file'], 'the propose command'),
                                         ('repository-entry ', ['REPOSITORY: the repository'], 'repository-entry command, naming your repository folder')):
            action = {'label': 'An action', 'available': True, 'command': command, 'cursor': command.index(' ') + 1, 'needs': needs,
                      'effects': 'It does a thing.', 'summary': 'A thing.'}
            for focus in (0, 1):
                text = ' '.join(' '.join(workbench_screens.actions_lines([action], focus, 100, 'P', '1' * 8 + '-1111-4111-8111-' + '1' * 12)).split())
                self.assertEqual(unresolved(text), [], (command, focus, text))
                if focus == 0:
                    self.assertIn(expected, text.lower())

    def test_the_help_typed_details_keep_their_synopses_and_say_what_capitals_mean(self):
        import inspect
        from intune_iac import workbench, workbench_screens
        self.assertIn('synopsis', inspect.signature(workbench_screens.details_lines).parameters)
        text = ' '.join(' '.join(workbench_screens.details_lines(workbench.HELP, 100, synopsis=True)).split())
        self.assertIn('execute OPERATION_DIR', text)
        self.assertIn('companion FILE', text)
        self.assertIn(workbench_screens.SYNOPSIS_CONVENTION, text)
        self.assertNotIn('the execute command', text)

    def test_the_interrupted_collection_line_names_the_service_folder_in_words(self):
        from intune_iac import entry, readiness, workbench
        self.assertIn('SERVICE', entry.FILL_IN_TEMPLATES)
        self.assertIn('SERVICE', readiness.TEMPLATE_WORDS)
        lines = workbench.interrupted_lines({'store_root': '/s', 'interrupted_during': {'command': 'collect'}})
        text = ' '.join(' '.join(map(str, lines)).split())
        self.assertEqual(unresolved(text), [], text)
        self.assertIn('--service-root as your service folder', text)



class RoundThreeAdditionsTests(unittest.TestCase):
    def test_the_delivery_next_step_says_the_review_digest_in_words(self):
        from intune_iac import entry, readiness
        self.assertIn('EXACT_REVIEW_DIGEST', entry.FILL_IN_TEMPLATES)
        self.assertIn('EXACT_REVIEW_DIGEST', readiness.TEMPLATE_WORDS)
        step = 'Review the change (5). Approve before 12:00 with:\n  execute /ops/one EXACT_REVIEW_DIGEST'
        text = ' '.join(said(step).split())
        self.assertEqual(unresolved(step) and unresolved(text), [])
        self.assertIn('the execute command using /ops/one, naming the digest that the review shows', text)

    def test_a_field_name_in_capitals_is_not_left_in_prose_beside_a_command_said_in_words(self):
        for path in sorted(PACKAGE.glob('*.py')):
            self.assertNotIn('for the REVISION', path.read_text(encoding='utf-8'), path.name)



# -- the JSON forms that carry the "it asks for the revision" prose ------------------------------------------------------------

# Digests of the canonical JSON of every form that the six REVISION sites feed: the diagnostics result, the Inspector's attention and its
# next actions, and the repository status, for a stale intent and for a consumer mismatch. Only the fields shown to vary between runs are
# masked, each by its path (VOLATILE_PATHS below), and the temporary directories by name; every other hash and value is pinned exactly.
# The digests are the forms taken on fa3f022 with the one declared substitution applied ("it asks for the REVISION" becomes "it asks for
# the revision"); a test shows that substitution to be the only difference. The digests of the forms as they were on fa3f022 are beside them.
REVISION_FORMS = {
    'mismatch attention': ('7dca140efd4cb0ee', '8304920b9c2305a2'),
    'mismatch diagnostics': ('d2c0fdeec026ec73', '91f0f6f6f008ae5d'),
    'mismatch next_actions': ('eb3b755597124a31', '11211780fd5cca96'),
    'stale attention': ('755986f54aaed12f', 'dc8b581055af068e'),
    'stale diagnostics': ('7c5e7c49eb559e26', 'f56b23dc20455cd6'),
    'stale next_actions': ('c3680963be60f1de', 'eb653a08076cb0c1'),
    'stale repository-status': ('1e7f012212a05bd2', '32f5eff381224bd6'),
}
# the fields that differ between two runs of the same code (the intent id hashes the clock and the temporary path, the resolution digest
# the temporary path, and the record carries the time it was made), by path, for each form; no other field is masked
VOLATILE_KEYS = ('repository_intent_id', 'resolution_sha256', 'recorded_at')
VOLATILE_PATHS = {
    'mismatch attention': ['/signals/0/evidence/repository_intent_id'],
    'mismatch diagnostics': ['/signals/0/evidence/repository_intent_id'],
    'mismatch next_actions': [],
    'stale attention': ['/signals/0/evidence/repository_intent_id'],
    'stale diagnostics': ['/signals/0/evidence/repository_intent_id'],
    'stale next_actions': [],
    'stale repository-status': ['/freshness/resolution_sha256', '/recorded_at', '/repository_intent_id'],
}


def _mask(value, path, masked, temps):
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            here = path + '/' + str(key)
            if key in VOLATILE_KEYS:
                masked.append(here)
                out[key] = 'VARIES'
            else:
                out[key] = _mask(child, here, masked, temps)
        return out
    if isinstance(value, list):
        return [_mask(child, '%s/%d' % (path, i), masked, temps) for i, child in enumerate(value)]
    if isinstance(value, str):
        for temp in temps:
            value = value.replace(str(temp), 'TEMP')
    return value


def _canonical(value, *temps):
    masked = []
    out = _mask(value, '', masked, temps)
    return json.dumps(out, sort_keys=True, indent=1), sorted(set(masked))


def _text_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class RevisionJsonPinsTests(unittest.TestCase):
    def forms(self):
        import copy
        from uuid import UUID
        import yaml
        from intune_iac import workbench, workbench_diagnostics, workbench_repository
        from plugin_tests import test_workbench_diagnostics as d
        out = {}
        for scenario in ('stale', 'mismatch'):
            case = d.DiagnosticsTests('test_a_healthy_policy_has_no_signals_and_says_what_was_checked')
            case.setUp()
            try:
                if scenario == 'stale':
                    case.import_intent()
                    case.edit_description('Edited in the repository.')
                else:
                    document = yaml.safe_load((case.repo / d.repository_tests.STACK).read_text())
                    policies = document['components']['terraform']['intune-reference']['vars']['policies']
                    policies['p_' + UUID(d.TENANT).hex + '_' + 'd' * 32] = copy.deepcopy(policies[d.repository_tests.KEY])
                    (case.repo / d.repository_tests.STACK).write_text(yaml.safe_dump(document))
                    case.import_intent()
                masks = (case.root, case.store.root)
                out[scenario + ' diagnostics'] = _canonical(workbench_diagnostics.diagnostics(case.store, d.OBJECT), *masks)
                attention = workbench._attention(case.store, d.OBJECT)
                out[scenario + ' attention'] = _canonical(attention, *masks)
                out[scenario + ' next_actions'] = _canonical(workbench._next_actions({}, attention, True), *masks)
                if scenario == 'stale':
                    out['stale repository-status'] = _canonical(workbench_repository.status(case.store, d.OBJECT), *masks)
            finally:
                case.doCleanups()
        return out

    def test_a_hash_that_is_not_volatile_is_pinned_exactly(self):
        # changing one stable 64-digit value to another changes the digest: the pin no longer hides every hash
        found = self.forms()
        text, _ = found['stale diagnostics']
        hashes = re.findall(r'[0-9a-f]{64}', text)
        self.assertTrue(hashes or 'VARIES' in text)
        if hashes:
            changed = text.replace(hashes[0], '0' * 64)
            self.assertNotEqual(_text_digest(changed), REVISION_FORMS['stale diagnostics'][1])

    def test_the_json_forms_differ_from_fa3f022_only_by_the_declared_substitution(self):
        found = self.forms()
        self.assertEqual(sorted(found), sorted(REVISION_FORMS))
        for form, (text, masked) in sorted(found.items()):
            with self.subTest(form=form):
                self.assertEqual(masked, VOLATILE_PATHS[form])        # only these fields are masked, each by its path
                self.assertEqual(_text_digest(text), REVISION_FORMS[form][1])
                self.assertNotIn('the REVISION', text)
                # undoing the declared substitution gives the form as fa3f022 had it
                self.assertEqual(_text_digest(text.replace('asks for the revision', 'asks for the REVISION')), REVISION_FORMS[form][0])



# -- round 5: the external programs the product prints commands for -----------------------------------------------------------

class ExternalDialectTests(unittest.TestCase):
    def test_the_programs_come_from_the_products_own_tables(self):
        from intune_iac import readiness
        programs = getattr(readiness, 'external_programs', lambda: frozenset())()
        self.assertEqual(sorted(programs), ['atmos', 'az', 'gh', 'tofu'])

    def test_an_external_command_with_a_placeholder_is_words_and_its_explaining_legend_goes(self):
        from intune_iac import signin_facts
        self.assertEqual(said('Choose one with: ' + signin_facts.SUBSCRIPTION_STEP + '; then run this command again.'),
                         'Choose one with: the az account set command, naming --subscription as the subscription id or name; '
                         'then run this command again.')
        self.assertEqual(said('Run: ' + signin_facts.LOGOUT_STEP),
                         'Run: the az logout command, naming --username as the name of the account you signed in with '
                         '(the account name to sign out)')
        self.assertEqual(said('Make one active with: gh auth switch --user NAME (the login name to use), and remove the others'),
                         'Make one active with: the gh auth switch command, naming --user as the name of the account you signed in '
                         'with (the login name to use), and remove the others')

    def test_resolved_external_commands_keep_their_form(self):
        for text in ('Sign in with: az login --tenant 11111111-1111-4111-8111-111111111111; then run it again.',
                     'Run az account list --output json yourself to see the sign-in.', 'Run: gh auth status yourself to see it.',
                     'az cloud set --name AzureCloud', 'gh auth login'):
            self.assertEqual(said(text), text)

    def test_a_legend_that_only_explained_a_described_operand_never_doubles_beside_the_description(self):
        self.assertEqual(said('with --serve instead of --out FILE (the file name) it serves'),
                         'with --serve instead of --out (the file you name) it serves')
        self.assertNotRegex(said('az logout --username NAME (the account name to sign out)'), r'\)\s*\(')


class CheckSigninScreenTests(unittest.TestCase):
    """start and catalog with --check-signin, the az and gh stubbed as the sign-in tests stub them."""

    def screens(self, labels):
        import json as _json
        import shutil
        from unittest.mock import patch
        from plugin_tests import test_rendered_surfaces as sweep
        from plugin_tests.signin_fakes import FakeClis
        root = Path(__file__).resolve().parents[1]
        context = _json.loads((root / 'examples/context.json').read_text())['tenant_id']
        found = []
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'estate dir'
            folder.mkdir()
            shutil.copyfile(root / 'examples/context.json', folder / 'context.json')
            for case in sweep.signin_cases(context):
                label, provider, azure, github, phrase = case[:5]
                if label.split(': ', 1)[1] not in labels:
                    continue
                fakes = FakeClis()
                try:
                    fakes.answer('az', 'account', 'list', **azure)
                    with patch.dict(os.environ, {'PATH': fakes.path_entry() + os.pathsep + os.environ.get('PATH', '')}):
                        for argv in (['start', str(folder), '--goal', 'discover', '--check-signin', provider],
                                     ['catalog', str(folder), '--goal', 'discover', '--check-signin', provider]):
                            for width in (120, 60):
                                code, text, err = sweep.run_cli(argv, width)
                                found.append((label, argv[0], width, text))
                finally:
                    fakes.cleanup()
        return found

    def test_several_accounts_and_an_expired_subscription_print_words_with_no_doubled_legend(self):
        found = self.screens(('several accounts in the tenant', 'only an expired subscription'))
        self.assertEqual(len(found), 8)
        for label, route, width, text in found:
            with self.subTest(label=label, route=route, width=width):
                self.assertEqual(unresolved(text), [], text)
                flat = ' '.join(text.split())
                # an option, its description in brackets, and a second bracket that only repeats it (the product's own prose may
                # put two brackets together elsewhere)
                self.assertNotRegex(flat, r'--[a-z-]+ \([^()]*\) \([^()]*\)')
                self.assertNotIn('SUBSCRIPTION', flat)
                self.assertNotIn('--username NAME', flat)
        expired = ' '.join(' '.join(text for label, route, width, text in found if 'expired' in label and route == 'start').split())
        self.assertIn('the az account set command, naming --subscription as the subscription id or name', expired)


class SigninStatusTests(unittest.TestCase):
    def test_signin_status_says_the_subscription_and_logout_steps_in_words(self):
        from intune_iac import signin_facts
        report = {'status': 'warning', 'verdicts': {}}
        text = ' '.join(signin_facts._in_words('Choose one with: ' + signin_facts.SUBSCRIPTION_STEP + '. Or sign out the others with: '
                                               + signin_facts.LOGOUT_STEP + '.').split())
        self.assertEqual(unresolved(text), [], text)
        self.assertIn('the az account set command, naming --subscription as the subscription id or name', text)
        self.assertIn('the az logout command, naming --username as', text)
        source = (PACKAGE / 'signin_facts.py').read_text(encoding='utf-8')
        self.assertIn("_wrap(_in_words(verdict['next_step'])", source)
        self.assertIn("_wrap(_in_words(present['sentence'])", source)



# -- round 6, item 1: render only where the text is printed ---------------------------------------------------------------------

class RecordedTextStaysTests(unittest.TestCase):
    """The structured values and the raw record carry the recorded text; only the screens carry the words."""

    def test_the_execute_forms_and_the_workflow_continuation_are_the_recorded_text(self):
        from intune_iac import workbench_screens
        raw = workbench_screens._execute_forms('/ops/one')
        self.assertIn('execute /ops/one DIGEST', raw)
        self.assertIn('--approve-digest DIGEST', raw)
        self.assertNotIn('naming', raw)
        from plugin_tests import test_workflow_map as tw
        case = tw.RealStoreTests('test_a_prepared_change_waits_for_the_exact_digest')
        case.setUp()
        try:
            case.prepare()
            read, flow = case.flow()
            continuation = tw.by_id(flow)['approve_execute']['continuation']
            self.assertIn('execute %s DIGEST' % case.operation, continuation)
            self.assertNotIn('naming', continuation)
            # the screens say it in words
            rows = ' '.join(' '.join(map(str, tw.lines_of(flow, 100, focus='approve_execute'))).split())
            self.assertIn('the execute command using', rows)
            self.assertNotIn(' DIGEST', rows)
        finally:
            case.doCleanups()

    def test_the_reconcile_recovery_value_is_the_recorded_text_and_the_layers_say_it(self):
        from intune_iac import workbench_screens
        source = ' '.join((PACKAGE / 'workbench_tui.py').read_text(encoding='utf-8').split())
        self.assertIn("'recovery': 'Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.'}",
                      source)
        value = {'recovery': 'Use :reconcile OPERATION_DIR for explicit independent readback; never blindly replay execution.'}
        self.assertIn('Use :reconcile OPERATION_DIR', json.dumps(value))                      # the raw record layer shows the value as recorded
        details = ' '.join(' '.join(workbench_screens.details_lines(value, 100)).split())
        self.assertIn('the :reconcile command, naming the operation folder', details)          # the typed details layer says it
        self.assertNotIn('Use :reconcile OPERATION_DIR', details)



# -- round 6, items 2 and 3: option arity and strict heads ---------------------------------------------------------------------

class ReaderShapeTests(unittest.TestCase):
    def test_the_value_of_an_option_is_whatever_follows_it_even_a_word_that_is_also_prose(self):
        self.assertEqual(said('Run: intune-iac wizard --input for --output NEW_DIR.'),
                         'Run: the wizard command using --input for, naming --output as a new folder for the output.')
        self.assertEqual(said('Run: intune-iac wizard --input and --output NEW_DIR'),
                         'Run: the wizard command using --input and, naming --output as a new folder for the output')

    def test_the_arity_comes_from_the_command_line_parser(self):
        import argparse
        from intune_iac import cli, readiness
        table = getattr(readiness, 'option_values', lambda: {})()
        self.assertTrue(table, 'no arity table')
        self.assertIs(table[('workbench', 'init')]['--root'], True)
        flags = []
        pending = [(cli.parser(), ())]
        while pending:
            parser, path = pending.pop()
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    pending += [(sub, path + (name,)) for name, sub in action.choices.items()]
                elif action.option_strings and path:
                    for option in action.option_strings:
                        if option.startswith('--'):
                            self.assertIs(table[path][option], action.nargs != 0, (path, option))
                            if action.nargs == 0:
                                flags.append((path, option))
        self.assertTrue(flags, 'the parser has options that take no value')
        path, option = flags[0]
        self.assertIs(table[path][option], False)

    def test_a_valueless_option_does_not_take_the_next_word(self):
        from intune_iac import readiness
        table = getattr(readiness, 'option_values', lambda: {})()
        path, option = next(((p, o) for p, opts in table.items() for o, takes in opts.items() if takes is False), (None, None))
        self.assertIsNotNone(path)
        text = 'Run: intune-iac %s %s and then use --root STORE' % (' '.join(path), option)
        self.assertEqual(readiness.commands_in(text)[0][3][0], (option, None))

    def test_a_product_command_head_is_known_to_the_parser_or_it_is_not_a_command(self):
        sentence = 'The documentation says intune-iac supports --output FILE.'
        self.assertNotIn('the supports command', said(sentence))
        from intune_iac import readiness
        self.assertEqual(readiness.commands_in(sentence), [])

    def test_an_external_command_in_brackets_is_read(self):
        self.assertEqual(said('Try (az account show --subscription SUBSCRIPTION).'),
                         'Try (the az account show command, naming --subscription as the subscription id or name).')
        self.assertEqual(said('Try (az account show --subscription 1111).'), 'Try (az account show --subscription 1111).')



class CapitalisationContractTests(unittest.TestCase):
    def test_no_assertion_drops_the_first_letter_of_the_phrase_it_checks(self):
        for name in ('test_catalog_wording.py', 'test_start_standin.py'):
            text = (Path(__file__).resolve().parent / name).read_text(encoding='utf-8')
            self.assertNotIn("'apture command", text, name)       # "rupture command" would satisfy it



# -- round 6, item 5: the convention sentence on every help output ---------------------------------------------------------------

class HelpConventionTests(unittest.TestCase):
    @staticmethod
    def parsers():
        import argparse
        from intune_iac import cli
        found, pending = [], [(cli.parser(), ())]
        while pending:
            parser, path = pending.pop()
            found.append((path, parser))
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    pending += [(sub, path + (name,)) for name, sub in action.choices.items()]
        return found

    def test_every_help_output_says_what_capitals_mean(self):
        from intune_iac import readiness
        sentence = readiness.SYNOPSIS_CONVENTION if hasattr(readiness, 'SYNOPSIS_CONVENTION') else 'In command syntax, words in capitals stand for values you supply.'
        found = self.parsers()
        self.assertGreater(len(found), 100)                       # every parser and subparser of the command line
        for path, parser in found:
            with self.subTest(path=path):
                self.assertIn(sentence, ' '.join(parser.format_help().split()))

    def test_a_usage_error_prints_the_sentence_right_after_the_usage_block(self):
        import contextlib
        import io
        from intune_iac import workbench_screens
        sentence = workbench_screens.SYNOPSIS_CONVENTION
        for path, parser in self.parsers():
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                parser.error('expected one argument')
            self.assertEqual(caught.exception.code, 2)
            text = ' '.join(err.getvalue().split())
            with self.subTest(path=path):
                self.assertIn(sentence, text)
                self.assertLess(text.index('usage:'), text.index(sentence))
                self.assertLess(text.index(sentence), text.index('error: invalid arguments'))   # the parser never echoes a value, so its message is this one

    def test_the_sentence_is_built_once(self):
        from intune_iac import readiness, workbench_screens
        self.assertIs(workbench_screens.SYNOPSIS_CONVENTION, getattr(readiness, 'SYNOPSIS_CONVENTION', None))



# -- round 7: words that refer to nothing on the screen -------------------------------------------------------------------------

class ReferToNothingTests(unittest.TestCase):
    def test_item_1_the_capture_contact_does_not_name_a_placeholder_the_screen_no_longer_has(self):
        from intune_iac import readiness
        from plugin_tests.test_start_standin import ORDINARY, estate, render, render_catalog
        sentence = readiness.capture_contact('Run: intune-iac capture --tenant T --policy P --output NEW_DIR')
        self.assertIn('writes what it reads into the new folder for the output.', sentence)
        self.assertNotIn('NEW_DIR', sentence)
        with tempfile.TemporaryDirectory() as parent:
            estate(parent, ORDINARY)
            for route in ('built', 'plain', 'cli'):
                text = ' '.join(' '.join(render(route, parent, ORDINARY, 100, 'discover')).split())
                with self.subTest(route=route):
                    self.assertIn('writes what it reads into the new folder for the output.', text)
                    self.assertNotRegex(text, r'into NEW_DIR')
            for route in ('built', 'plain', 'cli'):
                text = ' '.join(' '.join(render_catalog(route, parent, ORDINARY, 100, 'discover')).split())
                with self.subTest(catalog=route):
                    self.assertNotRegex(text, r'into NEW_DIR')

    def test_item_2_the_actions_layer_names_the_needed_input_in_words(self):
        from intune_iac import workbench_screens
        for need, expected in (('FILE: where to write it', 'needs the file you name: where to write it'),
                               ('REPOSITORY: the repository', 'needs your repository folder: the repository'),
                               ('DESIRED_JSON: the desired file', 'needs your desired-policy JSON file: the desired file'),
                               ('REVISION: the commit', 'needs the Git revision to record: the commit')):
            action = {'label': 'An action', 'available': True, 'command': 'x ', 'cursor': 2, 'needs': [need],
                      'effects': 'It does a thing.', 'summary': 'A thing.'}
            text = ' '.join(' '.join(workbench_screens.actions_lines([action], 0, 100, 'P', '1' * 8 + '-1111-4111-8111-' + '1' * 12)).split())
            with self.subTest(need=need):
                self.assertIn(expected, text)
                self.assertNotIn(need.split(':')[0] + ':', text)

    def test_item_3_the_typing_hint_says_what_to_type_not_a_capitalised_word(self):
        from intune_iac import workbench_tui
        mechanics = workbench_tui.Workspace._mechanics
        for need, expected in (('FILE: x', 'Type the file you name at the cursor.'),
                               ('REPOSITORY: x', 'Type your repository folder at the cursor.'),
                               ('DESIRED_JSON: x', 'Type your desired-policy JSON file at the cursor.')):
            forms = mechanics(None, {'needs': [need]}, bound=False)
            with self.subTest(need=need):
                self.assertEqual(forms[0], expected)
                from intune_iac import entry
                self.assertFalse(any(word in entry.FILL_IN_TEMPLATES for form in forms for word in re.findall(r'[A-Z][A-Z_]+', form)), forms)
        bound = mechanics(None, {'needs': []}, bound=True)
        self.assertEqual(bound[0], 'Type the full 40-character commit hash at the cursor; the digest after it pins the difference you reviewed.')
        self.assertFalse(any('REVISION' in form for form in bound), bound)

    def test_item_4_the_convention_sentence_is_a_row_of_the_chrome_of_every_help_page(self):
        import types
        from intune_iac import workbench_tui
        shows = workbench_tui.Workspace._shows_synopses
        help_view = types.SimpleNamespace(tab=7, value={'navigation': ['start [DIRECTORY]']}, layer='summary')
        details = types.SimpleNamespace(tab=7, value={'navigation': ['start [DIRECTORY]']}, layer='details')
        other = types.SimpleNamespace(tab=0, value={'objects': []}, layer='summary')
        self.assertTrue(shows(help_view))
        self.assertTrue(shows(details))
        self.assertFalse(shows(other))
        source = ' '.join((PACKAGE / 'workbench_tui.py').read_text(encoding='utf-8').split())
        self.assertIn('convention = word_wrap_rows(SYNOPSIS_CONVENTION, width) if self._shows_synopses() else []', source)
        self.assertIn('len(band) - len(convention)', source)             # the rows are counted before the body is sized
        self.assertNotIn('PinnedRow(row) for row in word_wrap(SYNOPSIS_CONVENTION', (PACKAGE / 'workbench_screens.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()

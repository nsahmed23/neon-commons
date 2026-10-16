"""PKG-TEXT-GUARD item 1: the text-mode commands, read from the parser, not typed by hand."""
import unittest

from intune_iac import cli


def text_commands(parser):
    """The text-mode commands of a parser, read from the parser: every leaf command with a `--json` switch (its default is the
    readable form) or a `--format` choice named text."""
    found = set()

    def walk(node, path):
        subs = [a for a in node._actions if a.__class__.__name__ == '_SubParsersAction']
        if not subs:
            options = {opt: act for act in node._actions for opt in act.option_strings}
            if '--json' in options or 'text' in (getattr(options.get('--format'), 'choices', None) or ()):
                found.add(' '.join(path))
            return
        for action in subs:
            for name, child in action.choices.items():
                if name in action._name_parser_map and action._name_parser_map[name] is child:
                    walk(child, path + [name])

    walk(parser, [])
    return found


TEXT_COMMANDS = {'start', 'catalog', 'engineering', 'simulate', 'signin status', 'signin collect', 'workbench workflow'}


class InventoryTests(unittest.TestCase):
    def test_the_text_mode_commands_are_the_ones_the_parser_exposes(self):
        # Read from the parser, not typed: a command added with a --json switch or a text --format fails here until the sweep
        # below (and the route test) name it. `workbench workspace` and `workbench terminal` are interactive screens with no
        # switch; their output does not pass through cli.py (see the report), so they are not in this inventory.
        self.assertEqual(text_commands(cli.parser()), TEXT_COMMANDS)


if __name__ == '__main__':
    unittest.main()

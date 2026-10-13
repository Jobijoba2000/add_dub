"""Check translation keys and formatting fields; inventory untranslated Qt text."""
import ast
import json
from pathlib import Path
import string
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from add_dub.i18n import TRANSLATIONS
from add_dub.gui.translations import LABELS, MESSAGES, LANGUAGE_INDEX


def audit():
    english = TRANSLATIONS['en']
    keys = set(english)
    formatter = string.Formatter()
    def fields(value):
        return sorted(field for _, field, _, _ in formatter.parse(value) if field is not None)
    catalogues = {
        language: {
            'count': len(values), 'missing': sorted(keys - set(values)),
            'extra': sorted(set(values) - keys),
            'format_mismatches': [key for key in sorted(keys & set(values))
                                  if fields(values[key]) != fields(english[key])]
        } for language, values in TRANSLATIONS.items()
    }
    interface_values = {**LABELS, **MESSAGES}
    interface_catalogues = {
        language: {
            'count': sum(len(values) == 4 and bool(values[index]) for values in interface_values.values()),
            'missing': sorted(key for key, values in interface_values.items()
                              if len(values) != 4 or not values[index]),
            'format_mismatches': sorted(key for key, values in interface_values.items()
                                       if len(values) == 4 and fields(values[index]) != fields(key)),
            'newline_mismatches': sorted(key for key, values in interface_values.items()
                                        if len(values) == 4 and values[index].count('\n') != key.count('\n')),
        } for language, index in LANGUAGE_INDEX.items()
    }
    used, ui_used, graphical = set(), set(), []
    # These APIs display text directly. Other dynamically assembled labels
    # require manual inspection; this is a lower bound, not a completeness claim.
    constructors = {'QLabel', 'QPushButton', 'QCheckBox', 'QGroupBox', 'QRadioButton'}
    methods = {'setText', 'setWindowTitle', 'setToolTip', 'setAccessibleName',
               'setFormat', 'addAction', 'addTab', 'addItem', 'setPlaceholderText'}
    for path in sorted((ROOT / 'add_dub').rglob('*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else '')
            arg = node.args[0]
            if name == 't' and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                used.add(arg.value)
            if name == 'ui' and isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                ui_used.add(arg.value)
            if ('gui' in path.parts and name in constructors | methods
                    and isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                    and any(character.isalpha() for character in arg.value)
                    and arg.value not in ('add_dub', 'CC', '%v/%m')):
                graphical.append({'file': str(path.relative_to(ROOT)), 'line': node.lineno, 'text': arg.value})
    return {'catalogues': catalogues, 'undefined_used_keys': sorted(used - keys),
            'interface': {'common_labels_in_five_languages': len(LABELS),
                          'messages_in_five_languages': len(MESSAGES),
                          'catalogues': interface_catalogues,
                          'undefined_used_keys': sorted(ui_used - set(interface_values))},
            'qt_literal_count': len(graphical), 'qt_literals': graphical,
            'scope': 'Literal calls only; GUI menus, model labels and dynamically assembled strings need manual review.'}


if __name__ == '__main__':
    result = audit()
    output = ROOT / 'tmp' / 'release-audit' / 'i18n.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'qt_literals'}, ensure_ascii=False, indent=2))
    if result['undefined_used_keys'] or result['interface']['undefined_used_keys'] or any(
            entry['missing'] or entry['extra'] or entry['format_mismatches']
            for entry in result['catalogues'].values()) or any(
            entry['missing'] or entry['format_mismatches'] or entry['newline_mismatches']
            for entry in result['interface']['catalogues'].values()):
        raise SystemExit(1)

"""Literal native formats from the reviewed sources, without opening a knowledge DB."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

from liuyao_mcp.canonical import CanonicalDocument, CanonicalPage

spec = importlib.util.spec_from_file_location('verify_manual_casts', Path(__file__).parents[1] / 'scripts/verify_manual_casts.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PAINTING = '妻财戌土Ｘ 子孙巳火\n官鬼申金″\n子孙午火′应\n兄弟卯木″\n子孙巳火″\n父母子水（伏） 妻财未土″世'
DAUGHTER = '官鬼寅木′应\n妻财子水″\n兄弟戌土″\n子孙申金 兄弟丑土X世 妻财亥水\n官鬼卯木○ 兄弟丑土\n父母巳火′'
DOTS = '妻财子水、、应\n兄弟戌土、\n子孙申金、、\n官鬼卯木、、世\n父母巳火、、\n兄弟未土、、'
SLASH = '官鬼寅木′\n妻财子水″\n兄弟戌土″应\n妻财亥水′\n父母午火/ 兄弟丑土″\n官鬼卯木′世'


def verify(rows, values, month='午', day='丁亥'):
    lines = [f'{month}月{day}日', *rows.splitlines()]
    text = '\n'.join(lines)
    digest = hashlib.sha256(text.encode()).hexdigest()
    document = CanonicalDocument({'source_id': 'literal_fixture'}, digest, text, digest, lines,
                                 {None: CanonicalPage(lines, 0, {})}, [])
    date = [{'page': None, 'start_line': 1, 'end_line': 1}]
    unit = {'unit_id': 'literal_fixture', 'parts': {'chart': [{'page': None, 'start_line': 2, 'end_line': 7}]},
            'cast': {'line_values': values, 'month_branch': month, 'day_ganzhi': day,
                     'field_spans': {'month_branch': date, 'day_ganzhi': date}}}
    return module.verify(document, unit)


@pytest.mark.parametrize('rows,values', [
    (PAINTING, [2, 2, 2, 1, 2, 0]), (DAUGHTER, [1, 3, 0, 2, 2, 1]),
    (DOTS, [2, 2, 2, 2, 1, 2]), (SLASH, [1, 2, 1, 2, 2, 1]),
])
def test_native_hidden_columns_and_dot_symbols(rows, values):
    assert verify(rows, values)['status'] == 'passed'


@pytest.mark.parametrize('original,replacement,check', [
    ('子孙申金', '子孙酉金', 'hidden_branch'),
    ('妻财亥水', '妻财子水', 'changed_branch'),
])
def test_hidden_and_changed_labels_are_still_verified(original, replacement, check):
    with pytest.raises(ValueError, match=check + "': False"):
        verify(DAUGHTER.replace(original, replacement), [1, 3, 0, 2, 2, 1])


def test_missing_source_branch_is_not_reconstructed():
    rows = '官鬼巳火′应\n父母未土″\n兄弟酉金′\n父母辰土′世\n妻财木′\n子孙子水′'
    with pytest.raises(ValueError, match='incomplete literal label at 2'):
        verify(rows, [1, 1, 1, 1, 2, 1], '寅', '庚戌')


def test_wrong_manual_moving_value_is_not_certified():
    # A wrong second value changes the palace and would otherwise misleadingly
    # report a first-row label conflict before reaching the transcription error.
    with pytest.raises(ValueError, match='literal line_value conflict at 2: source=2, manual=3'):
        verify(DOTS, [2, 3, 2, 2, 1, 2])

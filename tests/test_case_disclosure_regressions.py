"""Late dialogue remains source evidence, outside the initial case query."""
import hashlib
from pathlib import Path
import sqlite3

import pytest

from liuyao_mcp.common import case_search_text
from liuyao_mcp.manual_ingest import build_database
from liuyao_mcp.retrieval import get_source, search_knowledge


ROOT = Path(__file__).resolve().parents[1]
CASE_ID = 'zengshan_buyi.manual.L06150C0000.case'
LATE_TEXT = '彼曰，医空不药矣。'
INITIAL_BACKGROUND = '如午月癸丑日\n问来人病得几时，彼曰三月病起，'


@pytest.fixture(scope='module')
def disclosure_database(tmp_path_factory):
    shared = ROOT/'data/knowledge.sqlite'
    before = hashlib.sha256(shared.read_bytes()).hexdigest() if shared.exists() else None
    path = tmp_path_factory.mktemp('case-disclosure')/'knowledge.sqlite'
    build_database(ROOT, path)
    after = hashlib.sha256(shared.read_bytes()).hexdigest() if shared.exists() else None
    assert after == before
    return path


def test_initial_wife_question_keeps_early_illness_history_only(disclosure_database):
    case = get_source(CASE_ID, max_chars=500000, db_path=disclosure_database)['structured_case']
    question = case['question']
    assert question['question_only'] == '占妻病'
    assert question['known_background'] == question['background'] == INITIAL_BACKGROUND
    assert question['raw'] == '占妻病\n'+INITIAL_BACKGROUND
    assert LATE_TEXT not in case_search_text(case)
    assert '三月病起' in case_search_text(case)
    assert [(span['start_line'], span['start_column'], span['end_column'])
            for span in question['background_spans']] == [(6150, 0, 6), (6178, 0, 15)]


def test_initial_and_full_fts_respect_the_disclosure_boundary(disclosure_database):
    with sqlite3.connect(disclosure_database) as db:
        for table, expected in [('search_index', []), ('case_text_index', [(CASE_ID,)])]:
            rows = db.execute(f'SELECT evidence_id FROM {table} WHERE {table} MATCH ? AND evidence_id=?',
                              ('"医 空 不 药 矣"', CASE_ID)).fetchall()
            assert rows == expected
        assert db.execute('SELECT evidence_id FROM search_index WHERE search_index MATCH ? AND evidence_id=?',
                          ('"三月 病 起"', CASE_ID)).fetchall() == [(CASE_ID,)]
    options = dict(kind='case', outline_ids=['manual_unit:'+CASE_ID], retrieval_mode='bm25',
                   max_chars=500000, db_path=disclosure_database)
    assert search_knowledge('医', case_text_scope='initial', **options)['items'] == []
    full = search_knowledge('医', case_text_scope='full', **options)['items']
    assert [item['evidence_id'] for item in full] == [CASE_ID]


def test_full_source_retains_exact_late_dialogue_flags_and_chart(disclosure_database):
    source = get_source(CASE_ID, max_chars=500000, db_path=disclosure_database)
    case = source['structured_case']
    assert LATE_TEXT in source['text'] and '医家' not in source['text']
    assert hashlib.sha256(source['text'].encode('utf8')).hexdigest() == (
        'a280384a295d718f653499c171c8d8d7734d451262b0b3ddb3b2d7e6d1396ac8')
    background = case['parts']['background']
    assert background['exact_text'] == INITIAL_BACKGROUND+'\n'+LATE_TEXT
    for key in ('source_spans', 'canonical_spans'):
        early, late = background[key][1:]
        assert early['start_line'] == early['end_line'] == 6178
        assert (early['start_column'], early['end_column']) == (0, 15)
        assert early.get('eligible_for_initial_blind_input') is not False
        assert late['start_line'] == late['end_line'] == 6178
        assert (late['start_column'], late['end_column']) == (32, 41)
        assert late['disclosure_phase'] == 'after_initial_prediction'
        assert late['eligible_for_initial_blind_input'] is False
        assert 'L6178:C15-C32' in late['disclosure_basis']
        assert 'C32-C41' in late['disclosure_basis'] and LATE_TEXT in late['disclosure_basis']
    assert case['event_id'] == case['duplicate_group'] == 'zengshan-l11106-wife-illness'
    assert case['cast']['line_values'] == [2, 2, 2, 3, 1, 2]
    assert (case['cast']['month_branch'], case['cast']['day_ganzhi']) == ('午', '癸丑')
    assert case['cast']['verification']['evidence_sha256'] == (
        '66c834771726ba1ea286a727a9548d86e69af4c9de6c2d120b23bafdf89e41e0')
    assert case['quality']['status'] == 'eligible'


def test_work_transfer_recast_keeps_its_own_question_and_prior_context(disclosure_database):
    unit_id = 'liuyao_xiangfa_jinjie_xia-p0097-work-transfer-repeat'
    sources = [get_source(unit_id+suffix, max_chars=500000, db_path=disclosure_database)
               for suffix in ('', '.cast2')]
    first, second = [source['structured_case'] for source in sources]
    background = '求测人：男，手工指定（起卦方式）'
    recast_reason = ('本卦同为上一卦卦主所测，卦主认为自己能力不差，'
                     '不太愿意接受上一卦的结论，要求重新测一卦。')
    assert first['question']['question_only'] == '占问事宜：测工作调动能否成功'
    assert first['question']['known_background'] == background
    assert second['question']['question_only'] == '占问事宜：再测工作调动能否成功'
    assert second['question']['known_background'] == background+'\n'+recast_reason
    assert '再测工作调动' not in case_search_text(first)
    assert recast_reason not in case_search_text(first)
    assert recast_reason in case_search_text(second)
    for index, case in enumerate((first, second)):
        assert case['cast_index'] == index
        assert all(span['cast_index'] == index for span in case['question']['source_spans'])
        assert all(span['cast_index'] == index for span in case['question']['background_spans'])
    assert sources[0]['text'] == sources[1]['text']
    assert recast_reason in sources[0]['text']
    assert '反馈：调动不成功，死活就是办不成。' in sources[0]['text']


@pytest.mark.parametrize('case_id,late_text,phase,before,after', [
    ('zengshan_buyi.manual.L02026C0000.case',
     '彼问：卦中午火发动，寅木虽动，不克辰土。',
     'during_interpretation', '余说此卦辰土、未土、戌土、三重父母爻', '须待丑日'),
    ('zengshan_buyi.manual.L05366C0000.case',
     '问应何时见煤？', 'after_initial_prediction', '许其可开。', '应在六月。'),
])
def test_late_dialogue_keeps_its_actual_phase(
        disclosure_database, case_id, late_text, phase, before, after):
    source = get_source(case_id, max_chars=500000, db_path=disclosure_database)
    case = source['structured_case']
    assert late_text not in case['question']['raw']
    assert late_text not in case_search_text(case)
    assert late_text in case['parts']['background']['exact_text']
    assert source['text'].index(before) < source['text'].index(late_text) < source['text'].index(after)
    for key in ('source_spans', 'canonical_spans'):
        late = next(span for span in case['parts']['background'][key]
                    if span.get('disclosure_phase') == phase)
        assert late['eligible_for_initial_blind_input'] is False
        assert late['disclosure_phase'] == phase


def test_gift_feedback_precedes_recast_and_is_not_its_outcome(disclosure_database):
    unit_id = 'zengshan_pingshi_dxj-l14150-friend-gift-two'
    sources = [get_source(unit_id+suffix, max_chars=500000, db_path=disclosure_database)
               for suffix in ('', '.cast2')]
    first, second = [source['structured_case'] for source in sources]
    gift = '余随即出而与之，'
    assert first['question']['known_background'] == ''
    assert second['question']['known_background'] == gift
    assert first['outcome']['quotes'] == [gift]
    assert second['outcome']['quotes'] == ['果不得。']
    assert [span['cast_index'] for span in first['outcome']['source_spans']] == [0]
    assert [span['cast_index'] for span in second['outcome']['source_spans']] == [1]
    assert sources[0]['text'] == sources[1]['text']
    assert sources[0]['text'].index(gift) < sources[0]['text'].index('命其再占')
    assert '果不得。' in sources[0]['text']


def test_book_purchase_cast_does_not_inherit_south_trip_success(disclosure_database):
    unit_id = 'zengshan_pingshi_dxj-l12838-south-trip-four'
    sources = [get_source(unit_id+suffix, max_chars=500000, db_path=disclosure_database)
               for suffix in ('', '.cast2', '.cast3', '.cast4')]
    travel_feedback = ('即于巳日起程，\n竟行，后至地头，已二月矣。\n'
                       '余于彼地三四五月，了无宁日。')
    for source in sources[:3]:
        case = source['structured_case']
        assert case['quality']['status'] == 'eligible'
        assert case['question']['question_only'] == '余占南行'
        assert '奇门一部' not in case_search_text(case)
        assert case['outcome']['quotes'] == [travel_feedback]
    purchase = sources[3]['structured_case']
    assert purchase['cast_index'] == 3
    assert purchase['question']['question_only'] == '命余同去买之'
    assert '奇门一部' in purchase['question']['known_background']
    assert purchase['quality']['status'] == 'noise'
    assert purchase['outcome']['status'] == 'none'
    assert purchase['outcome']['quotes'] == purchase['outcome']['source_spans'] == []
    assert purchase['cast']['feedback_spans'] == []
    for source in sources:
        assert source['text'] == sources[0]['text']
        assert '命余同去买之。同道两日，余卜一卦' in source['text']
        assert '竟行，后至地头，已二月矣。' in source['text']

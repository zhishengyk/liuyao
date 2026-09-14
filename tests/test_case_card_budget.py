from copy import deepcopy

import pytest

from liuyao_mcp.common import dumps
from liuyao_mcp.retrieval import case_summary, get_source


OMITTED_CAST_FIELDS = ('evidence', 'field_spans', 'diagram_spans', 'transcription_review')


def sample_case(validation, verification, quality):
    return {
        'case_id': 'sample.cast2',
        'cast': {
            'line_values': [1, 2, 0, 1, 2, 1], 'month_branch': '午', 'day_ganzhi': '壬辰',
            'year_ganzhi': None, 'date': None, 'time': None,
            'calendar_basis': 'manual_transcription', 'line_values_basis': 'manual_transcription',
            'unknown_fields': ['year_ganzhi', 'date', 'time'],
            'unknown_note': '原文未给年份，不从反馈补齐',
            'verification': {'status': verification, 'evidence': 'audit.json', 'evidence_sha256': 'abc'},
            'evidence': {'line_values': {'exact_text': '完整逐字段凭证' * 400}},
            'field_spans': [{'start_line': 1, 'end_line': 8}],
            'diagram_spans': [{'exact_text': '原图全部爻行' * 200}],
            'transcription_review': {'status': verification, 'basis': '逐图抄录', 'image_path': 'chart.png'},
        },
        'reported_chart': {'primary': '原卦名', 'raw_header': '原始标题', 'line_text': ['旧行']},
        'features': {'chart_feature_status': validation, 'yongshen_candidates': [{'scope': 'hidden', 'moving': None}]},
        'interpretations': [{'author': '原作者', 'method_hint': 'lifa', 'yongshen_reported': ['父母'],
                             'original_text': '完整解释与适用条件。' * 250,
                             'cast_index': 1, 'cast_attribution': 'specified',
                             'source_spans': [{'start_line': 9, 'end_line': 10}],
                             'canonical_spans': [{'page': 2, 'start_line': 1, 'end_line': 2}]}],
        'outcome': {'status': 'reported_explicit', 'quotes': ['完整反馈，不能截短。']},
        'extraction': {'chart_validation': validation, 'source_chart_independently_verified': verification == 'verified'},
        'quality': {'status': quality, 'reason': '保留原审核说明'},
        'cast_index': 1,
        'cast_sequence': [{'case_id': 'sample', 'cast_index': 0}, {'case_id': 'sample.cast2', 'cast_index': 1}],
        'related_case_ids': ['sample'], 'author_yongshen': {'scope': 'hidden'},
        'duplicate_group': 'sample.event', 'duplicate_candidates': ['sample'],
    }


@pytest.mark.parametrize('validation,verification,quality', [
    ('calculated', 'verified', 'eligible'),
    ('not_run', 'needs_review', 'pending'),
    ('conflict', 'not_reviewed', 'noise'),
])
def test_case_card_only_omits_cast_proofs_and_keeps_status_and_identity(validation, verification, quality):
    case = sample_case(validation, verification, quality)
    before = deepcopy(case)
    card = case_summary(case)
    assert case == before
    assert card['cast'] == {key: value for key, value in before['cast'].items() if key not in OMITTED_CAST_FIELDS}
    assert card['cast_provenance'] == {
        'omitted_fields': list(OMITTED_CAST_FIELDS),
        'get_source': {'evidence_id': 'sample.cast2'},
        'transcription_review_status': verification,
    }
    for key in ('features', 'outcome', 'extraction', 'quality', 'cast_index', 'cast_sequence',
                'related_case_ids', 'author_yongshen', 'duplicate_group', 'duplicate_candidates'):
        assert card[key] == before[key]
    assert card['reported_chart'] == {'primary': '原卦名', 'raw_header': '原始标题'}
    interpretation = card['interpretations'][0]
    assert interpretation['quote'] == before['interpretations'][0]['original_text']
    assert interpretation['has_more'] is False
    for key in ('author', 'method_hint', 'yongshen_reported', 'cast_index', 'cast_attribution', 'source_spans', 'canonical_spans'):
        assert interpretation[key] == before['interpretations'][0][key]
    assert '同事件其他记录' in card['event_records_note']
    assert '不一定同盘或同一阶段' in card['event_records_note']
    assert len(dumps(card)) < len(dumps({**card, 'cast': before['cast']})) - 3000


def test_case_without_verbose_cast_fields_does_not_claim_provenance_was_omitted():
    case = sample_case('not_run', 'needs_review', 'pending')
    for key in OMITTED_CAST_FIELDS:
        case['cast'].pop(key)
    case.pop('duplicate_group')
    case.pop('duplicate_candidates')
    case.pop('quality')
    card = case_summary(case)
    assert card['cast'] == case['cast']
    assert 'cast_provenance' not in card and 'event_records_note' not in card
    assert 'duplicate_group' not in card and 'duplicate_candidates' not in card
    assert card['quality']['status'] == 'pending'


@pytest.mark.parametrize('evidence_id', [
    'liuyao_lifa_jinjie.manual.p0215_uncle_critical',
    'zengshan_pingshi_dxj.manual.l21102.cast2',
    'zengshan_buyi.manual.L06294C0000.case',
])
def test_get_source_keeps_full_cast_proofs_after_search_card_summary(evidence_id):
    source = get_source(evidence_id, max_chars=500000)
    before = deepcopy(source)
    complete = source['structured_case']
    card = case_summary(complete)
    assert source == before
    assert card['cast_provenance']['get_source']['evidence_id'] == evidence_id
    assert get_source(max_chars=500000, **card['cast_provenance']['get_source']) == before
    for field in card['cast_provenance']['omitted_fields']:
        assert field not in card['cast']
        assert complete['cast'][field] == before['structured_case']['cast'][field]
    for key in ('extraction', 'quality', 'cast_index', 'cast_sequence', 'related_case_ids',
                'duplicate_group', 'duplicate_candidates'):
        if key in complete:
            assert card[key] == complete[key]
    assert card['cast']['verification'] == complete['cast']['verification']

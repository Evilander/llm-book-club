"""The reader and TTS must never receive JSON syntax as discussion prose."""
import json

import pytest

from app.discussion.analysis_stream import AnalysisStream


@pytest.mark.parametrize("fenced,ascii_only,citations_first", [(False, False, False), (True, True, False), (False, True, True)])
def test_every_split_of_structured_reply(fenced, ascii_only, citations_first):
    prose = 'A 🌿 at the gate.\nShe says "stay". Café [1]'
    payload = {"analysis": prose, "citations": [{"quote": 'A quoted "analysis": "decoy"', "analysis": "nested decoy"}]}
    if citations_first:
        payload = dict(reversed(list(payload.items())))
    raw = json.dumps(payload, ensure_ascii=ascii_only)
    if fenced:
        raw = '```json\n' + raw + '\n```'
    for split in range(len(raw) + 1):
        stream = AnalysisStream()
        assert stream.feed(raw[:split]) + stream.feed(raw[split:]) == prose
    stream = AnalysisStream()
    assert ''.join(stream.feed(char) for char in raw) == prose


def test_text_arrives_before_citations_and_no_surrogate_escapes_leak():
    stream = AnalysisStream()
    assert stream.feed('{"analysis":"The gate ') == 'The gate '
    assert stream.feed('\\ud83c') == ''
    assert stream.feed('\\udf3f opens [1]"') == '🌿 opens [1]'
    assert stream.feed(',"citations":[{"quote":"secret source fields"}]}') == ''


def test_plain_legacy_replies_still_stream():
    stream = AnalysisStream()
    assert stream.feed('A quiet ') == 'A quiet '
    assert stream.feed('morning.') == 'morning.'

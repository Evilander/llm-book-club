"""Deterministic claim-to-evidence response validation."""

import json

import pytest
from pydantic import ValidationError

from app.discussion.grounded_response import (
    GroundedResponseInput,
    parse_grounded_response,
    validate_grounded_response,
)


def payload(chunk_id: str, quote: str) -> dict:
    return {
        "segments": [
            {
                "id": "s1",
                "kind": "interpretation",
                "text": "The image makes the moment feel suspended.",
                "citation_ids": ["c1"],
            },
            {
                "id": "s2",
                "kind": "question",
                "text": "Did that suspension feel peaceful or ominous to you?",
                "citation_ids": [],
            },
        ],
        "citations": [{"id": "c1", "chunk_id": chunk_id, "quote": quote}],
    }


def test_verified_claim_and_uncited_question_survive(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    response = GroundedResponseInput.model_validate(
        payload(chunk.id, "The morning sun cast long shadows")
    )

    result = validate_grounded_response(
        mock_db,
        response,
        allowed_chunk_ids=[chunk.id],
    )

    assert [segment["id"] for segment in result.segments] == ["s1", "s2"]
    assert result.citations[0]["segment_ids"] == ["s1"]
    assert result.citations[0]["verified"] is True
    assert result.metrics["retained_claim_segments"] == 1
    assert "peaceful or ominous" in result.content


def test_uncited_claim_is_dropped_but_question_survives(mock_db):
    response = GroundedResponseInput.model_validate(
        {
            "segments": [
                {
                    "id": "claim",
                    "kind": "grounded_claim",
                    "text": "The narrator is ashamed.",
                    "citation_ids": [],
                },
                {
                    "id": "question",
                    "kind": "question",
                    "text": "What did you notice?",
                    "citation_ids": [],
                },
            ],
            "citations": [],
        }
    )

    result = validate_grounded_response(mock_db, response, allowed_chunk_ids=[])

    assert [segment["id"] for segment in result.segments] == ["question"]
    assert result.dropped_segments[0]["reason"] == "claim_missing_citation"
    assert "narrator is ashamed" not in result.content


def test_altered_quote_drops_attached_interpretation(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    response = GroundedResponseInput.model_validate(
        payload(chunk.id, "A fabricated sentence that never appears")
    )

    result = validate_grounded_response(
        mock_db,
        response,
        allowed_chunk_ids=[chunk.id],
    )

    assert [segment["id"] for segment in result.segments] == ["s2"]
    assert result.invalid_citations[0]["verified"] is False
    assert result.dropped_segments[0]["reason"] == "claim_has_invalid_citation"


def test_mixed_valid_and_invalid_citations_drop_claim(mock_db, sample_book):
    first, second = sample_book["chunks"][:2]
    response = GroundedResponseInput.model_validate(
        {
            "segments": [
                {
                    "id": "s1",
                    "kind": "grounded_claim",
                    "text": "The two passages echo one another.",
                    "citation_ids": ["good", "bad"],
                }
            ],
            "citations": [
                {"id": "good", "chunk_id": first.id, "quote": "The morning sun"},
                {"id": "bad", "chunk_id": second.id, "quote": "never written here"},
            ],
        }
    )

    result = validate_grounded_response(
        mock_db,
        response,
        allowed_chunk_ids=[first.id, second.id],
    )

    assert result.segments == []
    assert result.citations == []
    assert result.metrics["dropped_segments"] == 1


def test_valid_quote_outside_slice_drops_claim(mock_db, sample_book):
    chunk = sample_book["chunks"][0]
    response = GroundedResponseInput.model_validate(
        payload(chunk.id, "The morning sun")
    )

    result = validate_grounded_response(
        mock_db,
        response,
        allowed_chunk_ids=[sample_book["chunks"][1].id],
    )

    assert [segment["id"] for segment in result.segments] == ["s2"]
    assert result.invalid_citations[0]["reason"] == "chunk outside session slice"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["segments"].append(dict(value["segments"][0])),
        lambda value: value["citations"].append(dict(value["citations"][0])),
        lambda value: value["segments"][0].update({"citation_ids": ["missing"]}),
        lambda value: value["segments"][0].update({"unexpected": True}),
    ],
)
def test_schema_rejects_duplicate_or_orphaned_ids_and_unknown_fields(
    sample_book,
    mutation,
):
    value = payload(sample_book["chunks"][0].id, "The morning sun")
    mutation(value)
    with pytest.raises(ValidationError):
        GroundedResponseInput.model_validate(value)


def test_parser_accepts_json_fence(sample_book):
    value = payload(sample_book["chunks"][0].id, "The morning sun")
    parsed = parse_grounded_response(f"```json\n{json.dumps(value)}\n```")
    assert parsed.segments[0].id == "s1"

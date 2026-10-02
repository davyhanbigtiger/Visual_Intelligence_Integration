import json

import pytest
from unittest.mock import patch

from visualintel.constants import DISCLAIMER_TEXT
from visualintel.engine import ModelCallError, call_model, format_answer, parse_model_response, answer_question, analyze_chunk
from visualintel.structured import FACTUAL_SCHEMA, REPORT_SCHEMA, validate_response
from visualintel.sampling import ChunkPlan


def report_data():
    return {
        "description": "A person lifts a white cup.", "unusual_flagged": False,
        "unusual_note": "", "guidance_assessment": "The walking area is not visible.",
        "guidance_suggestion": "There is insufficient evidence for a route.",
        "guidance_confidence": "low",
    }


def test_json_report_keeps_unicode_and_boolean():
    data = report_data()
    data["description"] = "人物拿起白色杯子。"
    assert parse_model_response(json.dumps(data, ensure_ascii=False)) == data


@pytest.mark.parametrize("changes", [
    {"unusual_flagged": "false"}, {"guidance_confidence": "certain"},
    {"description": " "}, {"unusual_flagged": True, "unusual_note": ""},
    {"unusual_note": "A cup."}, {"extra": 1},
])
def test_invalid_report_rejected(changes):
    data = report_data() | changes
    with pytest.raises(ModelCallError):
        parse_model_response(json.dumps(data))


def test_missing_required_field_rejected():
    with pytest.raises(ValueError):
        validate_response({"description": "Room."}, REPORT_SCHEMA)


def test_schema_and_options_sent_with_retry_for_bad_json():
    payloads = []
    def post(url, payload, timeout):
        payloads.append(payload)
        return {"response": "broken" if len(payloads) == 1 else '{"answer":"A cup."}'}
    assert call_model(["image"], "prompt", post_fn=post,
                      response_schema=FACTUAL_SCHEMA,
                      generation_options={"temperature": 0, "num_predict": 192}) == '{"answer":"A cup."}'
    assert len(payloads) == 2
    assert payloads[0]["format"] == FACTUAL_SCHEMA
    assert payloads[0]["options"]["num_predict"] == 192
    assert payloads[0]["think"] is False
    assert "previous response was rejected" in payloads[1]["prompt"]


def test_token_limit_failure_not_reported_as_success():
    with pytest.raises(ModelCallError, match="token limit"):
        call_model([], "prompt", response_schema=FACTUAL_SCHEMA,
                   post_fn=lambda *a: {"response": '{"answer":"A cup."}', "done_reason": "length"})


def test_json_factual_question_discards_model_guidance():
    raw = json.dumps({"answer": "A cup.", "guidance": "The path may be clear."})
    assert format_answer(raw, allow_guidance=False) == "A cup."


def test_json_advice_is_guarded_and_disclaimed():
    raw = json.dumps({"answer": "A hallway.", "guidance": "Go left."})
    result = format_answer(raw)
    assert "Go left" not in result
    assert "withheld" in result
    assert DISCLAIMER_TEXT in result


def test_report_pipeline_requests_structured_response(tiny_video):
    with patch("visualintel.engine.call_model", return_value=json.dumps(report_data())) as model:
        result = analyze_chunk(tiny_video, ChunkPlan(0, [0], 0, 0))
    assert result.status == "ok"
    assert model.call_args.kwargs["response_schema"] == REPORT_SCHEMA
    assert model.call_args.kwargs["generation_options"]["temperature"] == 0


def test_explicit_question_mode_overrides_keyword_guess(tiny_video):
    with patch("visualintel.engine.call_model", return_value='{"answer":"The word safe is visible."}') as model:
        result = answer_question(tiny_video, ChunkPlan(0, [0], 0, 0),
                                 "Does the label say safe?", question_mode="factual")
    assert result == "The word safe is visible."
    assert model.call_args.kwargs["response_schema"] == FACTUAL_SCHEMA


def test_conditional_command_cannot_bypass_guard():
    data = report_data() | {"guidance_suggestion": "If needed, ensure the mug is clean."}
    assert "withheld" in parse_model_response(json.dumps(data))["guidance_suggestion"]


def test_json_answer_can_quote_legacy_heading_without_being_truncated():
    text = "The sign reads GUIDANCE: Information desk."
    assert format_answer(json.dumps({"answer": text}), allow_guidance=False) == text

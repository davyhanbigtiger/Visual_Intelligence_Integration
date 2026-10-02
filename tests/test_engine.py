from visualintel.engine import format_answer, parse_model_response
from visualintel.constants import DISCLAIMER_TEXT


def test_parse_model_response_well_formatted():
    raw = (
        "DESCRIPTION: A person walks across a room and picks up a cup.\n"
        "UNUSUAL: no\n"
        "UNUSUAL_NOTE: \n"
        "ASSESSMENT: The room looks calm and there is nothing concerning.\n"
        "SUGGESTION: If moving through, the path in the middle of the room looks clear.\n"
        "CONFIDENCE: medium\n"
    )

    fields = parse_model_response(raw)

    assert fields["description"] == "A person walks across a room and picks up a cup."
    assert fields["unusual_flagged"] is False
    assert fields["unusual_note"] == ""
    assert fields["guidance_assessment"] == "The room looks calm and there is nothing concerning."
    assert fields["guidance_suggestion"] == "If moving through, the path in the middle of the room looks clear."
    assert fields["guidance_confidence"] == "medium"


def test_parse_model_response_flags_unusual():
    raw = (
        "DESCRIPTION: Something moves quickly near the door.\n"
        "UNUSUAL: yes\n"
        "UNUSUAL_NOTE: A fast motion near the doorway that is hard to identify.\n"
        "ASSESSMENT: This could be worth a closer look.\n"
        "SUGGESTION: It might help to pause and listen before proceeding toward the door.\n"
        "CONFIDENCE: low\n"
    )

    fields = parse_model_response(raw)

    assert fields["unusual_flagged"] is True
    assert fields["unusual_note"] == "A fast motion near the doorway that is hard to identify."


def test_parse_model_response_falls_back_when_unstructured():
    raw = "It's hard to tell what is happening here, the image is too blurry."

    fields = parse_model_response(raw)

    assert fields["description"] == raw
    assert fields["unusual_flagged"] is False
    assert fields["guidance_confidence"] == "low"
    assert fields["guidance_assessment"] == ""
    assert fields["guidance_suggestion"] == ""


def test_parse_model_response_rejects_invalid_confidence():
    raw = "DESCRIPTION: A quiet hallway.\nCONFIDENCE: extremely-sure\n"

    fields = parse_model_response(raw)

    assert fields["guidance_confidence"] == "low"


def test_format_answer_appends_guidance_and_disclaimer_when_present():
    raw = (
        "ANSWER: There are two people sitting at a table.\n"
        "GUIDANCE: The space between the chairs looks about a meter wide, "
        "which may be enough to pass through carefully.\n"
    )

    result = format_answer(raw)

    assert result == (
        "There are two people sitting at a table.\n\n"
        "The space between the chairs looks about a meter wide, "
        "which may be enough to pass through carefully.\n\n"
        f"{DISCLAIMER_TEXT}"
    )


def test_format_answer_skips_guidance_for_factual_questions():
    raw = "ANSWER: There are three cups on the table.\n"

    result = format_answer(raw)

    assert result == "There are three cups on the table."


def test_format_answer_falls_back_to_raw_text_when_unstructured():
    raw = "The scene shows a hallway."

    result = format_answer(raw)

    assert result == "The scene shows a hallway."

import cv2
import numpy as np

from visualintel.engine import extract_frames


def test_extract_frames_returns_requested_frames_as_jpeg_bytes(tiny_video):
    frames = extract_frames(tiny_video, [0, 5, 9])

    assert len(frames) == 3
    for raw_bytes in frames:
        decoded = cv2.imdecode(np.frombuffer(raw_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape == (16, 16, 3)


def test_extract_frames_raises_for_missing_file():
    import pytest
    from visualintel.engine import extract_frames

    with pytest.raises(FileNotFoundError):
        extract_frames("does_not_exist.mp4", [0])

import pytest

from visualintel.engine import (
    EngineNotReadyError,
    ModelCallError,
    call_model,
    check_ollama_ready,
)


def test_check_ollama_ready_passes_when_model_is_listed():
    def fake_get(url, timeout):
        return {"models": [{"name": "minicpm-v4.6:latest"}, {"name": "llama3:latest"}]}

    check_ollama_ready(model="minicpm-v4.6", get_fn=fake_get)  # should not raise


def test_check_ollama_ready_raises_when_server_unreachable():
    def fake_get(url, timeout):
        raise OSError("connection refused")

    with pytest.raises(EngineNotReadyError, match="Cannot reach Ollama"):
        check_ollama_ready(get_fn=fake_get)


def test_check_ollama_ready_raises_when_model_missing():
    def fake_get(url, timeout):
        return {"models": [{"name": "llama3:latest"}]}

    with pytest.raises(EngineNotReadyError, match="not found"):
        check_ollama_ready(model="minicpm-v4.6", get_fn=fake_get)


def test_call_model_returns_response_text():
    def fake_post(url, payload, timeout):
        assert payload["think"] is False
        assert payload["model"] == "minicpm-v4.6"
        return {"response": "DESCRIPTION: a quiet room\n"}

    result = call_model(["base64data"], "describe this", post_fn=fake_post)

    assert result == "DESCRIPTION: a quiet room\n"


def test_call_model_retries_once_then_succeeds():
    calls = []

    def flaky_post(url, payload, timeout):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("timeout")
        return {"response": "ok"}

    result = call_model(["base64data"], "describe this", post_fn=flaky_post)

    assert result == "ok"
    assert len(calls) == 2


def test_call_model_raises_after_retry_exhausted():
    def always_fails(url, payload, timeout):
        raise OSError("timeout")

    with pytest.raises(ModelCallError):
        call_model(["base64data"], "describe this", post_fn=always_fails)

from unittest.mock import patch

from visualintel.engine import ChunkResult, analyze_chunk, answer_question
from visualintel.sampling import ChunkPlan


def test_analyze_chunk_returns_ok_result_on_success(tiny_video):
    chunk = ChunkPlan(chunk_index=0, frame_indices=[0, 5], start_time=0.0, end_time=0.5)
    canned_response = (
        "DESCRIPTION: A calm room.\n"
        "UNUSUAL: no\n"
        "UNUSUAL_NOTE: \n"
        "ASSESSMENT: Looks calm.\n"
        "SUGGESTION: The doorway ahead looks clear.\n"
        "CONFIDENCE: high\n"
    )

    with patch("visualintel.engine.call_model", return_value=canned_response):
        result = analyze_chunk(tiny_video, chunk)

    assert result == ChunkResult(
        chunk_index=0,
        start_time=0.0,
        end_time=0.5,
        status="ok",
        description="A calm room.",
        unusual_flagged=False,
        unusual_note="",
        guidance_assessment="Looks calm.",
        guidance_suggestion="The doorway ahead looks clear.",
        guidance_confidence="high",
        error=None,
    )


def test_analyze_chunk_returns_failed_result_when_model_call_fails(tiny_video):
    from visualintel.engine import ModelCallError

    chunk = ChunkPlan(chunk_index=1, frame_indices=[0], start_time=0.0, end_time=0.0)

    with patch("visualintel.engine.call_model", side_effect=ModelCallError("boom")):
        result = analyze_chunk(tiny_video, chunk)

    assert result.status == "failed"
    assert result.chunk_index == 1
    assert "boom" in result.error


def test_answer_question_returns_formatted_answer(tiny_video):
    chunk = ChunkPlan(chunk_index=0, frame_indices=[0, 5], start_time=0.0, end_time=0.5)

    with patch(
        "visualintel.engine.call_model",
        return_value="ANSWER: There are no people visible.\n",
    ):
        answer = answer_question(tiny_video, chunk, "Is anyone in the room?")

    assert answer == "There are no people visible."

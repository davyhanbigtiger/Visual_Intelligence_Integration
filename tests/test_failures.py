import json
import io
from unittest.mock import patch

import pytest

from visualintel.cli import main
from visualintel.constants import DISCLAIMER_TEXT
from visualintel.engine import (
    EngineNotReadyError, ModelCallError, analyze_chunk, call_model,
    check_ollama_ready, extract_frames,
    format_answer, parse_model_response, answer_question,
)
from visualintel.report import build_report, save_report
from visualintel.sampling import ChunkPlan, plan_chunks, plan_single_chunk_over_video


@pytest.mark.parametrize("kwargs", [
    {"fps": float("nan")}, {"fps": 0}, {"interval_sec": 0},
    {"max_frames_per_chunk": 0}, {"max_chunks": -1},
])
def test_invalid_sampling_parameters(kwargs):
    args = {"total_frames": 100, "fps": 30}
    args.update(kwargs)
    with pytest.raises(ValueError):
        plan_chunks(**args)


def test_long_video_sampling_is_bounded():
    chunks, truncated = plan_chunks(10**12, 30)
    assert truncated and len(chunks) == 20
    assert sum(len(c.frame_indices) for c in chunks) == 160


def test_zero_ask_frames_rejected():
    with pytest.raises(ValueError):
        plan_single_chunk_over_video(100, 30, max_frames=0)


def test_exact_model_tag_required():
    with pytest.raises(EngineNotReadyError):
        check_ollama_ready("minicpm-v4.6:other", get_fn=lambda *a: {
            "models": [{"name": "minicpm-v4.6:latest"}]
        })


@pytest.mark.parametrize("response", ["", None, 42])
def test_invalid_model_response_retried_exactly_once(response):
    calls = []
    def post(*args):
        calls.append(args)
        return {"response": response}
    with pytest.raises(ModelCallError):
        call_model(["image"], "prompt", post_fn=post)
    assert len(calls) == 2


def test_decode_failure_is_not_silently_skipped(tiny_video):
    with pytest.raises(ModelCallError, match="Cannot decode frame"):
        extract_frames(tiny_video, [0, 9999])


def test_empty_frames_never_reach_model(tiny_video):
    with patch("visualintel.engine.call_model") as model:
        result = analyze_chunk(tiny_video, ChunkPlan(0, [], 0, 0))
    assert result.status == "failed"
    model.assert_not_called()


def test_failed_chunks_saved_and_nonzero_exit(tiny_video, tmp_path):
    out = tmp_path / "out"
    with patch("visualintel.cli.check_ollama_ready"), patch(
        "visualintel.engine.call_model", side_effect=ModelCallError("timeout")
    ):
        assert main(["report", tiny_video, "--output-dir", str(out)]) == 3
    data = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert data["chunks"][0]["status"] == "failed"
    assert "description" not in data["chunks"][0]


def test_existing_report_preserved(tmp_path):
    report = build_report("x.avi", 0, False, [])
    save_report(report, str(tmp_path))
    original = (tmp_path / "report.json").read_bytes()
    with pytest.raises(FileExistsError):
        save_report(build_report("changed.avi", 1, False, []), str(tmp_path))
    assert (tmp_path / "report.json").read_bytes() == original


def test_report_preserved_if_existence_check_becomes_stale(tmp_path):
    target = tmp_path / "report.json"
    target.write_text("preserve concurrent writer", encoding="utf-8")
    with patch("visualintel.report.Path.exists", return_value=False):
        with pytest.raises(FileExistsError):
            save_report(build_report("x.avi", 0, False, []), str(tmp_path))
    assert target.read_text(encoding="utf-8") == "preserve concurrent writer"


def test_unstructured_report_still_has_disclaimer(tiny_video, tmp_path):
    with patch("visualintel.cli.check_ollama_ready"), patch(
        "visualintel.engine.call_model", return_value="A blurry room."
    ):
        assert main(["report", tiny_video, "--output-dir", str(tmp_path)]) == 0
    assert DISCLAIMER_TEXT in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_missing_video_checked_before_model(capsys):
    with patch("visualintel.cli.check_ollama_ready") as readiness:
        assert main(["report", "does_not_exist.mp4"]) == 1
    readiness.assert_not_called()


def test_unwritable_output_has_clean_error(tiny_video, tmp_path, capsys):
    target = tmp_path / "file"
    target.write_text("preserve", encoding="utf-8")
    with patch("visualintel.cli.check_ollama_ready"), patch(
        "visualintel.engine.call_model", return_value="A room."
    ):
        assert main(["report", tiny_video, "--output-dir", str(target)]) == 1
    assert "ERROR:" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("command", ["Do not assume the path is safe.", "Go left.", "往左走。", "You must cross now.", "Consider the context."])
def test_obvious_commands_withheld(command):
    fields = parse_model_response(f"DESCRIPTION: A room.\nSUGGESTION: {command}\nCONFIDENCE: high")
    assert "withheld" in fields["guidance_suggestion"]
    assert fields["guidance_confidence"] == "low"
    answer = format_answer(f"ANSWER: Limited view.\nGUIDANCE: {command}")
    assert command not in answer
    assert DISCLAIMER_TEXT in answer


def test_cli_prints_chinese_to_windows_encoded_stream(tiny_video):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    with patch("visualintel.cli.sys.stdout", stream), patch(
        "visualintel.cli.check_ollama_ready"
    ), patch("visualintel.engine.call_model", return_value="ANSWER: 画面里有一个杯子。"):
        assert main(["ask", tiny_video, "有什么？"]) == 0
    stream.flush()
    assert "画面里有一个杯子。" in raw.getvalue().decode("utf-8")


def test_misspelled_guidance_from_real_model_still_has_disclaimer():
    raw = "ANSWER: A room.\nGUIDENCE: The setting appears calm."
    result = format_answer(raw)
    assert result == f"A room.\n\nThe setting appears calm.\n\n{DISCLAIMER_TEXT}"
    assert format_answer(raw.removeprefix("ANSWER: ")) == result


@pytest.mark.parametrize("question,advice", [
    ("What objects and actions are visible?", False),
    ("How should I get past this?", True),
    ("画面有什么？", False), ("应该怎么走？", True),
])
def test_question_controls_guidance_even_when_model_misclassifies(tiny_video, question, advice):
    chunk = ChunkPlan(0, [0], 0, 0)
    with patch("visualintel.engine.call_model", return_value="ANSWER: A room.\nGUIDANCE: The doorway might be clear."):
        result = answer_question(tiny_video, chunk, question)
    assert (DISCLAIMER_TEXT in result) is advice
    if not advice:
        assert result == "A room."


def test_advice_without_heading_is_guarded_and_has_disclaimer(tiny_video):
    with patch("visualintel.engine.call_model", return_value="Go left."):
        result = answer_question(tiny_video, ChunkPlan(0, [0], 0, 0), "How should I get past this?")
    assert "Go left" not in result
    assert "withheld" in result
    assert DISCLAIMER_TEXT in result

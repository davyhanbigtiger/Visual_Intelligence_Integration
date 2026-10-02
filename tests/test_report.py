import json

from visualintel.constants import DISCLAIMER_TEXT
from visualintel.engine import ChunkResult
from visualintel.report import build_report, render_markdown, save_report


def _ok_chunk():
    return ChunkResult(
        chunk_index=0,
        start_time=0.0,
        end_time=8.0,
        status="ok",
        description="A person walks across a calm room.",
        unusual_flagged=False,
        unusual_note="",
        guidance_assessment="The room looks calm.",
        guidance_suggestion="The path down the middle looks clear.",
        guidance_confidence="medium",
    )


def _failed_chunk():
    return ChunkResult(
        chunk_index=1,
        start_time=8.0,
        end_time=16.0,
        status="failed",
        description="",
        unusual_flagged=False,
        unusual_note="",
        guidance_assessment="",
        guidance_suggestion="",
        guidance_confidence="low",
        error="Model call failed after retry: timeout",
    )


def test_build_report_structures_chunks():
    report = build_report("videos/x.mp4", duration_sec=16.0, truncated=False,
                           chunk_results=[_ok_chunk(), _failed_chunk()])

    assert report["video"] == "videos/x.mp4"
    assert report["duration_sec"] == 16.0
    assert report["truncated"] is False
    assert len(report["chunks"]) == 2

    ok = report["chunks"][0]
    assert ok["status"] == "ok"
    assert ok["description"] == "A person walks across a calm room."
    assert ok["unusual_flag"] == {"flagged": False, "note": ""}
    assert ok["guidance"] == {
        "assessment": "The room looks calm.",
        "suggestion": "The path down the middle looks clear.",
        "confidence": "medium",
        "disclaimer": DISCLAIMER_TEXT,
    }

    failed = report["chunks"][1]
    assert failed["status"] == "failed"
    assert failed["error"] == "Model call failed after retry: timeout"
    assert "description" not in failed


def test_render_markdown_includes_key_content():
    report = build_report("videos/x.mp4", duration_sec=16.0, truncated=True,
                           chunk_results=[_ok_chunk(), _failed_chunk()])

    md = render_markdown(report)

    assert "videos/x.mp4" in md
    assert "A person walks across a calm room." in md
    assert "The path down the middle looks clear." in md
    assert DISCLAIMER_TEXT in md
    assert "Processing failed" in md
    assert "truncated" in md.lower()


def test_save_report_writes_utf8_json_and_markdown(tmp_path):
    report = build_report("videos/x.mp4", duration_sec=8.0, truncated=False,
                           chunk_results=[_ok_chunk()])

    json_path, md_path = save_report(report, str(tmp_path / "x"))

    saved = json.loads(open(json_path, encoding="utf-8").read())
    assert saved == report

    md_text = open(md_path, encoding="utf-8").read()
    assert DISCLAIMER_TEXT in md_text

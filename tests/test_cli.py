from unittest.mock import patch

from visualintel.cli import main
from visualintel.engine import EngineNotReadyError


def test_report_command_exits_cleanly_when_ollama_not_ready(tiny_video, capsys):
    with patch("visualintel.cli.check_ollama_ready", side_effect=EngineNotReadyError("not running")):
        code = main(["report", tiny_video])

    assert code == 2
    assert "not running" in capsys.readouterr().err


def test_report_command_writes_report_using_real_pipeline(tiny_video, tmp_path, capsys):
    canned_response = (
        "DESCRIPTION: A calm test scene.\n"
        "UNUSUAL: no\n"
        "UNUSUAL_NOTE: \n"
        "ASSESSMENT: Looks calm.\n"
        "SUGGESTION: Nothing obstructs the view.\n"
        "CONFIDENCE: high\n"
    )
    output_dir = str(tmp_path / "out")

    with patch("visualintel.cli.check_ollama_ready", return_value=None), \
         patch("visualintel.engine.call_model", return_value=canned_response):
        code = main(["report", tiny_video, "--output-dir", output_dir])

    assert code == 0
    assert "Report written to" in capsys.readouterr().out

    import json
    report = json.loads(open(f"{output_dir}/report.json", encoding="utf-8").read())
    assert report["chunks"][0]["description"] == "A calm test scene."


def test_report_command_preserves_chunk_order_under_concurrency(tiny_video, tmp_path):
    import time

    from visualintel.engine import ChunkResult
    from visualintel.sampling import ChunkPlan

    fake_chunks = [
        ChunkPlan(chunk_index=i, frame_indices=[0], start_time=float(i), end_time=float(i) + 1)
        for i in range(4)
    ]

    def fake_analyze_chunk(video_path, chunk, model="minicpm-v4.6"):
        # later chunks sleep less, so if execution order controlled result
        # order we'd see it scrambled — executor.map must keep input order
        # regardless of which finishes first
        time.sleep(0.05 * (4 - chunk.chunk_index))
        return ChunkResult(
            chunk_index=chunk.chunk_index,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            status="ok",
            description=f"chunk {chunk.chunk_index}",
            unusual_flagged=False,
            unusual_note="",
            guidance_assessment="",
            guidance_suggestion="",
            guidance_confidence="low",
        )

    output_dir = str(tmp_path / "out")
    with patch("visualintel.cli.check_ollama_ready", return_value=None), \
         patch("visualintel.cli.plan_chunks", return_value=(fake_chunks, False)), \
         patch("visualintel.cli.analyze_chunk", side_effect=fake_analyze_chunk):
        code = main(["report", tiny_video, "--output-dir", output_dir])

    assert code == 0
    import json
    report = json.loads(open(f"{output_dir}/report.json", encoding="utf-8").read())
    descriptions = [c["description"] for c in report["chunks"]]
    assert descriptions == ["chunk 0", "chunk 1", "chunk 2", "chunk 3"]


def test_ask_command_prints_answer(tiny_video, capsys):
    with patch("visualintel.cli.check_ollama_ready", return_value=None), \
         patch("visualintel.engine.call_model", return_value="ANSWER: Nothing unusual.\n"):
        code = main(["ask", tiny_video, "Is anything unusual?"])

    assert code == 0
    assert "Nothing unusual." in capsys.readouterr().out


def test_report_command_errors_on_missing_video(capsys):
    with patch("visualintel.cli.check_ollama_ready", return_value=None):
        code = main(["report", "does_not_exist.mp4"])

    assert code == 1
    assert "Cannot open video" in capsys.readouterr().err

import json
from pathlib import Path

from visualintel.constants import DISCLAIMER_TEXT
from visualintel.engine import ChunkResult


def chunk_result_to_dict(c: ChunkResult) -> dict:
    d = {
        "start_time": c.start_time,
        "end_time": c.end_time,
        "status": c.status,
    }
    if c.status == "failed":
        d["error"] = c.error
        return d
    d["description"] = c.description
    d["unusual_flag"] = {"flagged": c.unusual_flagged, "note": c.unusual_note}
    d["guidance"] = {
        "assessment": c.guidance_assessment,
        "suggestion": c.guidance_suggestion,
        "confidence": c.guidance_confidence,
        "disclaimer": DISCLAIMER_TEXT,
    }
    return d


def build_report(
    video_path: str,
    duration_sec: float,
    truncated: bool,
    chunk_results: list[ChunkResult],
) -> dict:
    return {
        "video": video_path,
        "duration_sec": duration_sec,
        "truncated": truncated,
        "chunks": [chunk_result_to_dict(c) for c in chunk_results],
    }


def render_markdown(report: dict) -> str:
    lines = [f"# Video Understanding Report: {report['video']}", ""]
    duration_line = f"Duration: {report['duration_sec']:.1f}s"
    if report["truncated"]:
        duration_line += " (truncated — only part of the video was processed)"
    lines.append(duration_line)
    lines.append("")

    lines.append("Confidence is the model's self-assessment, not a calibrated probability.")
    lines.append("")

    for chunk in report["chunks"]:
        lines.append(f"## [{chunk['start_time']:.1f}s - {chunk['end_time']:.1f}s]")
        if chunk["status"] == "failed":
            lines.append(f"_Processing failed: {chunk.get('error', 'unknown error')}_")
            lines.append("")
            continue

        lines.append(chunk["description"])
        if chunk["unusual_flag"]["flagged"]:
            lines.append(f"\n**Unusual:** {chunk['unusual_flag']['note']}")

        g = chunk["guidance"]
        if g["assessment"] or g["suggestion"]:
            lines.append(f"\n**Situational assessment:** {g['assessment']}")
            lines.append(f"**Suggestion:** {g['suggestion']} (confidence: {g['confidence']})")
        lines.append(f"\n> {g['disclaimer']}")
        lines.append("")

    return "\n".join(lines)


def save_report(report: dict, output_dir: str) -> tuple[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "report.json"
    md_path = out / "report.md"
    if json_path.exists() or md_path.exists():
        raise FileExistsError(f"Report already exists in {out}; choose a new --output-dir")
    with json_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2))
    with md_path.open("x", encoding="utf-8") as stream:
        stream.write(render_markdown(report))
    return str(json_path), str(md_path)

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cost_model.py"
spec = importlib.util.spec_from_file_location("cost_model", SCRIPT)
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)


def test_claude_token_formula_matches_vendor_doc_examples():
    assert cm.tokens_claude(200, 200) == 64          # doc table
    assert cm.tokens_claude(1000, 1000) == 1296      # doc table
    assert cm.tokens_claude(640, 480) == 414
    assert cm.tokens_claude(320, 240) == 108
    assert cm.tokens_claude(4000, 4000) == 1568      # standard-tier cap


def test_gemini_token_formula_matches_vendor_doc_example():
    assert cm.tokens_gemini(960, 540) == 1548        # doc example: 6 tiles
    assert cm.tokens_gemini(384, 384) == 258
    assert cm.tokens_gemini(320, 240) == 258
    assert cm.tokens_gemini(640, 480) == 1032        # 2 x 2 tiles


def test_api_cost_and_fx():
    assert cm.api_cost_usd(1_000_000, 0, 0.30, 2.50) == pytest.approx(0.30)
    assert cm.api_cost_usd(0, 1_000_000, 0.30, 2.50) == pytest.approx(2.50)
    assert cm.usd_to_cad(1.0) == pytest.approx(cm.FX_CAD_PER_USD)


def test_monthly_events_and_transfer():
    assert cm.monthly_events(fps=0.5, hours_per_day=8, trigger_rate=1.0) == pytest.approx(432_000)
    assert cm.monthly_events(fps=0.5, hours_per_day=8, trigger_rate=0.05) == pytest.approx(21_600)
    assert cm.transfer_seconds(50_000, 5) == pytest.approx(0.08)
    assert cm.monthly_gb(100_000, 50_000) == pytest.approx(5.0)


def test_breakeven_and_gpu_rental():
    assert cm.breakeven_events_per_month(240, 24, 0.001) == pytest.approx(10_000)
    assert cm.serverless_cost_per_event_usd(3.60, 0.5) == pytest.approx(0.0005)
    assert cm.rented_pod_month_usd(0.5, 2) == pytest.approx(30.0)


def test_report_renders_all_sections():
    text = cm.report()
    for heading in ("Per-event API cost", "Monthly API cost", "Rented GPU", "Break-even", "Upload size and time"):
        assert heading in text
    assert "| 640x480 | 51.7 |" in text  # measured median JPEG size appears in the upload table

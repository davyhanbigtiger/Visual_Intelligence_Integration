"""Parametric cost / latency / data-volume model for the local-vs-remote split.

Every price and latency below is an *input* with a source and a verification status; the
formulas are deterministic and unit-tested. Nothing here calls a paid service. Re-run with
updated numbers when prices change -- several of these moved by tens of percent in 2026.
"""
import math

FX_CAD_PER_USD = 1.4246  # Bank of Canada daily rate for 2026-10-02 (via search snippet, page not fetched)

# --- tokenization formulas (from the providers' own documentation) -----------------------

def tokens_claude(width: int, height: int) -> int:
    """platform.claude.com vision doc: ceil(w/28) * ceil(h/28), capped at 1568 on the standard tier."""
    return min(math.ceil(width / 28) * math.ceil(height / 28), 1568)


def tokens_gemini(width: int, height: int) -> int:
    """ai.google.dev image-understanding doc: 258 if both sides <= 384, else 258 per 768px tile
    with crop unit floor(min(w, h) / 1.5) (doc example: 960x540 -> 6 tiles -> 1548 tokens)."""
    if width <= 384 and height <= 384:
        return 258
    crop = math.floor(min(width, height) / 1.5)
    return 258 * math.ceil(width / crop) * math.ceil(height / crop)


# --- cost / latency / volume formulas ----------------------------------------------------

def api_cost_usd(in_tokens: int, out_tokens: int, in_per_m: float, out_per_m: float) -> float:
    return in_tokens * in_per_m / 1e6 + out_tokens * out_per_m / 1e6


def monthly_events(fps: float, hours_per_day: float, trigger_rate: float, days: int = 30) -> float:
    """Heavy-model calls per month: frames/s x active seconds/day x fraction passing the local gate."""
    return fps * 3600 * hours_per_day * trigger_rate * days


def transfer_seconds(payload_bytes: float, uplink_mbps: float) -> float:
    return payload_bytes * 8 / (uplink_mbps * 1e6)


def monthly_gb(events: float, payload_bytes: float) -> float:
    return events * payload_bytes / 1e9


def breakeven_events_per_month(hardware_usd: float, amortize_months: int, cost_per_event_usd: float) -> float:
    """Event rate above which buying hardware (amortized, ignoring power/ops) beats paying per event."""
    return hardware_usd / (amortize_months * cost_per_event_usd)


def serverless_cost_per_event_usd(rate_per_hour_usd: float, busy_seconds: float) -> float:
    return rate_per_hour_usd / 3600 * busy_seconds


def rented_pod_month_usd(rate_per_hour_usd: float, hours_per_day: float, days: int = 30) -> float:
    return rate_per_hour_usd * hours_per_day * days


def usd_to_cad(usd: float) -> float:
    return usd * FX_CAD_PER_USD


# --- scenario report ---------------------------------------------------------------------

# status: OFFICIAL = read from the vendor's own page on 2026-10-03; VENDOR = vendor/community claim,
# not independently verified; MEASURED = measured on this project's laptop; ASSUMED = my assumption.
PRICES = {
    "gemini-3.5-flash-lite": {"in": 0.30, "out": 2.50, "status": "OFFICIAL (ai.google.dev pricing, updated 2026-10-01; out incl. thinking tokens)"},
    "claude-haiku-4.5": {"in": 1.00, "out": 5.00, "status": "in=OFFICIAL (vision doc example); out=ASSUMED $5/M, not fetched"},
    "qwen3-vl-flash": {"in": 0.05, "out": 0.40, "status": "OFFICIAL (Alibaba Model Studio, Singapore region); image-token count ASSUMED"},
}
RUNPOD_SERVERLESS_4090_PER_HOUR = 1.10   # OFFICIAL runpod.io/pricing
RUNPOD_POD_4090_COMMUNITY_PER_HOUR = 0.34  # OFFICIAL runpod.io/pricing
JETSON_ORIN_NANO_SUPER_USD = 399          # per CNX Software 2026-07-22 (old $249); NVIDIA store showed out of stock
RPI5_16GB_USD = 305                       # OFFICIAL raspberrypi.com (16GB variant)
RPI_AI_HAT2_USD = 200                     # OFFICIAL raspberrypi.com (Hailo-10H, 40 TOPS INT4, 8GB)

SCENARIOS = {
    "occasional questions (200/day)": 200,
    "event-gated (2,000/day)": 2000,
    "8h/day at 0.5 fps, no gate (14,400/day)": 14400,
    "24h at 0.5 fps, no gate (43,200/day)": 43200,
}
# Median JPEG sizes from outputs/latency-bench-20261002 (12 frames per size, OpenCV default quality).
MEASURED_JPEG_BYTES = {"640x480": 51742, "480x360": 34188, "320x240": 17816}
UPLINK_MBPS = (1, 5, 20)  # ASSUMED scenarios: poor coverage / typical mobile / good 5G or Wi-Fi

TEXT_PROMPT_TOKENS = 100
OUT_TOKENS = 60  # ASSUMED short scene description


def per_event_usd(model: str, in_tokens: int) -> float:
    price = PRICES[model]
    return api_cost_usd(in_tokens + TEXT_PROMPT_TOKENS, OUT_TOKENS, price["in"], price["out"])


def report() -> str:
    lines = [f"FX: 1 USD = {FX_CAD_PER_USD} CAD", ""]
    sizes = {"640x480": (640, 480), "320x240": (320, 240)}
    lines.append("## Per-event API cost (USD) -- assumes 100 text-prompt tokens and 60 output tokens")
    lines.append("| model | image | image tokens | USD / event | CAD / 1000 events |")
    lines.append("|---|---|---:|---:|---:|")
    per_event = {}
    for model in PRICES:
        for name, (w, h) in sizes.items():
            tokens = {"gemini-3.5-flash-lite": tokens_gemini, "claude-haiku-4.5": tokens_claude,
                      "qwen3-vl-flash": lambda w, h: math.ceil(w / 32) * math.ceil(h / 32)}[model](w, h)
            cost = per_event_usd(model, tokens)
            per_event[(model, name)] = cost
            lines.append(f"| {model} | {name} | {tokens} | {cost:.6f} | {usd_to_cad(cost * 1000):.3f} |")
    lines += ["", "## Monthly API cost in CAD by usage scenario (640x480)", "| scenario | " +
              " | ".join(PRICES) + " |", "|---|" + "---:|" * len(PRICES)]
    for label, per_day in SCENARIOS.items():
        row = [f"{usd_to_cad(per_event[(m, '640x480')] * per_day * 30):.2f}" for m in PRICES]
        lines.append(f"| {label} | " + " | ".join(row) + " |")
    lines += ["", "## Rented GPU (RunPod, USD list prices) -> CAD per month",
              "| option | CAD / month |", "|---|---:|",
              f"| community 4090 pod, 24h/day | {usd_to_cad(rented_pod_month_usd(RUNPOD_POD_4090_COMMUNITY_PER_HOUR, 24)):.0f} |",
              f"| community 4090 pod, 8h/day | {usd_to_cad(rented_pod_month_usd(RUNPOD_POD_4090_COMMUNITY_PER_HOUR, 8)):.0f} |",
              f"| community 4090 pod, 2h/day | {usd_to_cad(rented_pod_month_usd(RUNPOD_POD_4090_COMMUNITY_PER_HOUR, 2)):.0f} |"]
    for busy in (0.5, 1.0):
        cost = serverless_cost_per_event_usd(RUNPOD_SERVERLESS_4090_PER_HOUR, busy)
        lines.append(f"| serverless 4090, {busy}s busy/event, 2,000 events/day (busy time only; "
                     f"excludes cold starts) | {usd_to_cad(cost * 2000 * 30):.0f} |")
    lines += ["", "## Break-even: hardware (amortized 24 months) vs per-event API (640x480)",
              "| hardware | USD | vs model | break-even events/day |", "|---|---:|---|---:|"]
    for name, usd in (("Jetson Orin Nano Super", JETSON_ORIN_NANO_SUPER_USD),
                      ("RPi5 16GB + AI HAT+ 2", RPI5_16GB_USD + RPI_AI_HAT2_USD)):
        for model in PRICES:
            events = breakeven_events_per_month(usd, 24, per_event[(model, "640x480")]) / 30
            lines.append(f"| {name} | {usd} | {model} | {events:,.0f} |")
    lines += ["", "## Upload size and time (JPEG bytes are MEASURED medians from this project's frames; "
              "uplink speeds are ASSUMED scenarios, not measurements)",
              "| image | JPEG KB | " + " | ".join(f"{m} Mbps (s)" for m in UPLINK_MBPS)
              + " | GB/month @2,000/day | GB/month @14,400/day |",
              "|---|---:|" + "---:|" * len(UPLINK_MBPS) + "---:|---:|"]
    for name, size in MEASURED_JPEG_BYTES.items():
        times = " | ".join(f"{transfer_seconds(size, m):.2f}" for m in UPLINK_MBPS)
        lines.append(f"| {name} | {size / 1000:.1f} | {times} | "
                     f"{monthly_gb(2000 * 30, size):.1f} | {monthly_gb(14400 * 30, size):.1f} |")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())

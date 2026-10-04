import base64
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

import cv2
import numpy as np

from visualintel.constants import DISCLAIMER_TEXT
from visualintel.sampling import ChunkPlan
from visualintel.structured import ADVICE_SCHEMA, FACTUAL_SCHEMA, REPORT_SCHEMA, validate_response

_FIELD_PATTERN = re.compile(
    r"^(DESCRIPTION|UNUSUAL_NOTE|UNUSUAL|ASSESSMENT|SUGGESTION|CONFIDENCE):\s*(.*)$",
    re.IGNORECASE,
)

_VALID_CONFIDENCE = ("low", "medium", "high")

# Conservative guard for obvious commands; this is not a semantic safety validator.
_COMMAND_PATTERN = re.compile(
    r"(?:^|[.!?。！？,;:\n]\s*)(?:do not\b|don't\b|go\b|turn\b|walk\b|move\b|"
    r"cross\b|use\b|consider\b|proceed\b|stop\b|pause\b|avoid\b|keep\b|"
    r"take\b|ensure\b|you must\b|you should\b|must\b|往[左右前后]|必须|请向|向[左右]走)",
    re.IGNORECASE,
)
_WITHHELD_GUIDANCE = (
    "The model's suggestion was withheld because it used command-like wording. "
    "The available frames do not establish a reliable action or route."
)


def _guard_report_fields(fields: dict) -> dict:
    if _COMMAND_PATTERN.search(fields["guidance_suggestion"]) or _COMMAND_PATTERN.search(fields["guidance_assessment"]):
        fields["guidance_assessment"] = "Only limited sampled frames are available."
        fields["guidance_suggestion"] = _WITHHELD_GUIDANCE
        fields["guidance_confidence"] = "low"
    return fields


def parse_model_response(raw_text: str) -> dict:
    """Validate JSON responses, retaining legacy text parsing for compatibility.

    Live calls enforce JSON before reaching this parser. Invalid JSON is an
    explicit model failure. Legacy unstructured text keeps the historical
    low-confidence fallback for saved responses and older clients.
    """
    if raw_text.lstrip().startswith("{"):
        try:
            return _guard_report_fields(validate_response(json.loads(raw_text), REPORT_SCHEMA))
        except ValueError as error:
            raise ModelCallError(f"Invalid structured report: {error}") from error
    fields = {
        "description": "",
        "unusual_flagged": False,
        "unusual_note": "",
        "guidance_assessment": "",
        "guidance_suggestion": "",
        "guidance_confidence": "low",
    }
    current_key = None
    for line in raw_text.splitlines():
        match = _FIELD_PATTERN.match(line.strip())
        if match:
            key, value = match.group(1).upper(), match.group(2).strip()
            if key == "DESCRIPTION":
                fields["description"] = value
                current_key = "description"
            elif key == "UNUSUAL":
                fields["unusual_flagged"] = value.strip().lower().startswith("y")
                current_key = None
            elif key == "UNUSUAL_NOTE":
                fields["unusual_note"] = value
                current_key = "unusual_note"
            elif key == "ASSESSMENT":
                fields["guidance_assessment"] = value
                current_key = "guidance_assessment"
            elif key == "SUGGESTION":
                fields["guidance_suggestion"] = value
                current_key = "guidance_suggestion"
            elif key == "CONFIDENCE":
                conf = value.strip().lower()
                fields["guidance_confidence"] = conf if conf in _VALID_CONFIDENCE else "low"
                current_key = None
        elif current_key and line.strip():
            fields[current_key] = (fields[current_key] + " " + line.strip()).strip()

    if not fields["description"]:
        fields["description"] = raw_text.strip()
        fields["guidance_confidence"] = "low"

    return _guard_report_fields(fields)


def format_answer(raw_text: str, allow_guidance: bool = True) -> str:
    """Render validated JSON or legacy ANSWER/GUIDANCE responses.

    The caller controls guidance inclusion. Question classification and
    mandatory disclaimers for advice are handled by answer_question.
    """
    if raw_text.lstrip().startswith("{"):
        try:
            data = json.loads(raw_text)
            schema = ADVICE_SCHEMA if isinstance(data, dict) and "guidance" in data else FACTUAL_SCHEMA
            validate_response(data, schema)
        except ValueError as error:
            raise ModelCallError(f"Invalid structured answer: {error}") from error
        answer = data["answer"].strip()
        if allow_guidance and data.get("guidance"):
            guidance = data["guidance"].strip()
            if _COMMAND_PATTERN.search(guidance) or _COMMAND_PATTERN.search(answer):
                answer = "Only limited sampled frames are available."
                guidance = _WITHHELD_GUIDANCE
            return f"{answer}\n\n{guidance}\n\n{DISCLAIMER_TEXT}"
        return answer
    answer_match = re.search(
        r"ANSWER:\s*(.*?)(?:\n\s*(?:GUIDANCE|GUIDENCE):|\Z)", raw_text, re.IGNORECASE | re.DOTALL
    )
    guidance_match = re.search(r"(?:GUIDANCE|GUIDENCE):\s*(.*)\Z", raw_text, re.IGNORECASE | re.DOTALL)

    answer = answer_match.group(1).strip() if answer_match else raw_text.strip()
    # Some models repeat the section heading inside ANSWER; only keep the
    # factual portion before the first guidance heading for factual questions.
    if not allow_guidance:
        return re.split(r"(?:GUIDANCE|GUIDENCE):", answer, maxsplit=1,
                        flags=re.IGNORECASE)[0].strip()
    if guidance_match:
        if not answer_match:
            answer = raw_text[:guidance_match.start()].strip()
        guidance = guidance_match.group(1).strip()
        if _COMMAND_PATTERN.search(guidance) or _COMMAND_PATTERN.search(answer):
            answer = "Only limited sampled frames are available."
            guidance = _WITHHELD_GUIDANCE
        return f"{answer}\n\n{guidance}\n\n{DISCLAIMER_TEXT}"
    return answer

def extract_frames(video_path: str, frame_indices: list[int]) -> list[bytes]:
    """Read specific frames from a video file and return them as
    JPEG-encoded bytes, ready for base64 encoding into an Ollama request.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")
    frames: list[bytes] = []
    try:
        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok:
                raise ModelCallError(f"Cannot decode frame {idx} from {video_path}")
            ok, buf = cv2.imencode(".jpg", frame)
            if ok:
                frames.append(buf.tobytes())
            else:
                raise ModelCallError(f"Cannot encode frame {idx}")
    finally:
        cap.release()
    return frames


def resize_encoded_image(image: bytes, max_side: int | None = None) -> bytes:
    """Optional aspect-preserving downsampling; never upscale smaller images."""
    if max_side is None:
        return image
    if type(max_side) is not int or max_side <= 0:
        raise ValueError("max_side must be a positive integer")
    frame = cv2.imdecode(np.frombuffer(image, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise ModelCallError("Cannot decode image for resizing")
    height, width = frame.shape[:2]
    if max(height, width) <= max_side:
        return image
    ratio = max_side / max(height, width)
    frame = cv2.resize(frame, (max(1, round(width * ratio)), max(1, round(height * ratio))),
                       interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise ModelCallError("Cannot encode resized image")
    return encoded.tobytes()

class EngineNotReadyError(RuntimeError):
    pass


class ModelCallError(RuntimeError):
    pass


_LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")


def default_base_url() -> str:
    """Model endpoint: http://localhost:11434 unless VISUALINTEL_OLLAMA_URL names another one.

    The override exists so the same code can talk to a local facade in front of a remote GPU reached through an
    SSH tunnel. Frames are never sent to a non-loopback host unless VISUALINTEL_ALLOW_NONLOOPBACK=1 is set.
    """
    configured = os.environ.get("VISUALINTEL_OLLAMA_URL", "").strip().rstrip("/")
    if not configured:
        return "http://localhost:11434"
    parsed = urllib.parse.urlparse(configured)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise EngineNotReadyError(f"VISUALINTEL_OLLAMA_URL is not a usable URL: {configured}")
    if parsed.hostname not in _LOOPBACK_HOSTS and os.environ.get("VISUALINTEL_ALLOW_NONLOOPBACK") != "1":
        raise EngineNotReadyError(
            f"VISUALINTEL_OLLAMA_URL points at {parsed.hostname}, which is not loopback; "
            "set VISUALINTEL_ALLOW_NONLOOPBACK=1 only if you really intend to send frames there")
    return configured


def _http_post_json(url: str, payload: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_json(url: str, timeout: int) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_ollama_ready(
    model: str = "minicpm-v4.6",
    base_url: str | None = None,
    get_fn=None,
) -> None:
    base_url = base_url or default_base_url()
    get_fn = get_fn or _http_get_json
    try:
        data = get_fn(f"{base_url}/api/tags", 5)
    except Exception as e:
        raise EngineNotReadyError(
            f"Cannot reach Ollama at {base_url}. Is it running? ({e})"
        ) from e
    names = [m.get("name", "") for m in data.get("models", [])]
    requested = model if ":" in model.rsplit("/", 1)[-1] else model + ":latest"
    if not any((n if ":" in n.rsplit("/", 1)[-1] else n + ":latest") == requested for n in names):
        raise EngineNotReadyError(
            f"Model '{model}' not found in Ollama. Run: ollama pull {model}"
        )


def call_model(
    images_b64: list[str],
    prompt: str,
    model: str = "minicpm-v4.6",
    base_url: str | None = None,
    timeout: int = 300,
    post_fn=None,
    response_schema: dict | None = None,
    generation_options: dict | None = None,
) -> str:
    base_url = base_url or default_base_url()
    post_fn = post_fn or _http_post_json
    payload = {
        "model": model,
        "prompt": prompt,
        "images": images_b64,
        "stream": False,
        "think": False,
    }
    if response_schema is not None:
        payload["format"] = response_schema
    if generation_options is not None:
        payload["options"] = generation_options
    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            result = post_fn(f"{base_url}/api/generate", payload, timeout)
            response = result["response"]
            if not isinstance(response, str) or not response.strip():
                raise ValueError("Model returned an empty or invalid response")
            if response_schema is not None:
                if result.get("done_reason") == "length":
                    raise ValueError("Structured model output reached its token limit")
                validate_response(json.loads(response), response_schema)
            return response
        except Exception as e:
            last_error = e
            if response_schema is not None and isinstance(e, (ValueError, KeyError, TypeError)):
                payload = {**payload, "prompt": prompt + (
                    f"\nThe previous response was rejected: {e}. "
                    "Return every required field with the correct type, no extra fields. "
                    "Use shorter phrases to fit the output limit. Ensure unusual_flagged "
                    "and unusual_note are consistent if those fields are required."
                )}
    raise ModelCallError(f"Model call failed after retry: {last_error}")

_UNDERSTAND_PROMPT = """\
Describe what happens in these frames (sampled in order from a video clip),
then respond using EXACTLY this format, with each field on its own line:

DESCRIPTION: <objective description of what happens across the frames>
UNUSUAL: <yes or no>
UNUSUAL_NOTE: <if UNUSUAL is yes, describe what is unusual; otherwise leave blank>
ASSESSMENT: <a soft, hedged observation about whether the situation seems safe or needs caution>
SUGGESTION: <a soft, non-imperative suggestion with specific details when possible (distances, directions, objects); do not give commands>
CONFIDENCE: <low, medium, or high>

Do not use imperative commands like "go left" or "you must". Always phrase
suggestions as observations, and acknowledge you are working from limited
visual information.
Do not invent metric distances from monocular images. Mention distances only
when supported by visible scale or signage. Separate observations from guesses.
"""

_ASK_PROMPT_TEMPLATE = """\
Answer the following question about these video frames (sampled in order): "{question}"

Answer factually and directly, starting with "ANSWER:". Only if the question
is asking for advice, direction, or a judgment about safety or action (not a
purely factual question), add a second section starting with "GUIDANCE:"
that follows these rules: no imperative commands (avoid "go left", "you must
use X"), phrase it as an observation and a soft suggestion with specific
details when possible, and acknowledge you are working from limited visual
information. If the question is purely factual, do not add a GUIDANCE
section at all.
"""

STRUCTURED_REPORT_PROMPT = (
    "These video frames are in time order. Describe only visible actions briefly, "
    "distinguishing observations from uncertain inferences. Routine gestures or "
    "holding a cup are not unusual by themselves. Flag only visible unexpected or "
    "hazardous events. The assessment and suggestion must refer to visible evidence, "
    "not invented hygiene, tools, distances, or assumptions about the person. "
    "If the walking surface or route is not visible, explicitly state that a route "
    "cannot be assessed and use low guidance confidence. Do not declare overall safety "
    "from a close-up. Suggestions must be hedged observations ('appears', 'might', "
    "'could'), never commands, including commands after 'if'. Use concise English "
    "phrases. Return only JSON matching this schema: " + json.dumps(REPORT_SCHEMA)
)

_ADVICE_QUESTION = re.compile(
    r"\b(?:should|advice|recommend|safe|safety|danger|caution|route|navigate)\b|"
    r"\bwhich (?:way|direction)\b|\bhow (?:to|can i|do i)\b|"
    r"建议|该怎么|该如何|应该|如何|怎么走|怎么办|安全|危险|注意什么|绕行|绕过|往哪",
    re.IGNORECASE,
)


@dataclass
class ChunkResult:
    chunk_index: int
    start_time: float
    end_time: float
    status: str
    description: str
    unusual_flagged: bool
    unusual_note: str
    guidance_assessment: str
    guidance_suggestion: str
    guidance_confidence: str
    error: str | None = None


def _frames_to_b64(video_path: str, chunk: ChunkPlan) -> list[str]:
    frames = extract_frames(video_path, chunk.frame_indices)
    if not frames:
        raise ModelCallError("No frames decoded; refusing to ask the model without images")
    return [base64.b64encode(f).decode("utf-8") for f in frames]


def analyze_chunk(video_path: str, chunk: ChunkPlan, model: str = "minicpm-v4.6") -> ChunkResult:
    try:
        images_b64 = _frames_to_b64(video_path, chunk)
        raw = call_model(images_b64, STRUCTURED_REPORT_PROMPT, model=model,
                         response_schema=REPORT_SCHEMA,
                         generation_options={"temperature": 0, "seed": 42, "num_predict": 384})
        fields = parse_model_response(raw)
        return ChunkResult(
            chunk_index=chunk.chunk_index,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            status="ok",
            description=fields["description"],
            unusual_flagged=fields["unusual_flagged"],
            unusual_note=fields["unusual_note"],
            guidance_assessment=fields["guidance_assessment"],
            guidance_suggestion=fields["guidance_suggestion"],
            guidance_confidence=fields["guidance_confidence"],
        )
    except (ModelCallError, OSError, cv2.error) as e:
        return ChunkResult(
            chunk_index=chunk.chunk_index,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            status="failed",
            description="",
            unusual_flagged=False,
            unusual_note="",
            guidance_assessment="",
            guidance_suggestion="",
            guidance_confidence="low",
            error=str(e),
        )


SCENE_PROMPT = (
    "Describe the general environment in this image in one or two short sentences, "
    "at most 35 words. Mention the apparent setting, main people and prominent "
    "visible objects or posture. General categories such as room, person, cup "
    "are sufficient. Do not guess hidden contents, identities or intentions. "
    "Do not give safety judgments or advice. Return JSON with only an answer field."
)


def describe_scene(video_path: str, chunk: ChunkPlan, model: str = "minicpm-v4.6") -> str:
    """Describe a sampled instant, without detailed identification or advice."""
    raw = call_model(
        _frames_to_b64(video_path, chunk), SCENE_PROMPT,
        model=model, response_schema=FACTUAL_SCHEMA,
        generation_options={"temperature": 0, "seed": 42, "num_predict": 96},
    )
    return format_answer(raw, allow_guidance=False)


def answer_question(video_path: str, chunk: ChunkPlan, question: str, model: str = "minicpm-v4.6",
                    question_mode: str = "auto") -> str:
    if question_mode not in ("auto", "factual", "advice"):
        raise ValueError("question_mode must be auto, factual, or advice")
    images_b64 = _frames_to_b64(video_path, chunk)
    advice = question_mode == "advice" or (question_mode == "auto" and bool(_ADVICE_QUESTION.search(question)))
    schema = ADVICE_SCHEMA if advice else FACTUAL_SCHEMA
    prompt = (
        "Answer the question about these time-ordered video frames briefly (at most "
        "60 words per field). Use only visible evidence and acknowledge what is "
        "not visible. Do not invent distances or unseen actions. "
    )
    if advice:
        prompt += ("Give a specific hedged observation and suggestion, never commands. "
                   "If the route is not visible, say it cannot be assessed. ")
    else:
        prompt += "This is a factual question. Give observations only, without advice. "
    prompt += "Return only JSON matching this schema: " + json.dumps(schema)
    prompt += "\nQuestion: " + json.dumps(question, ensure_ascii=False)
    raw = call_model(images_b64, prompt, model=model, response_schema=schema,
                     generation_options={"temperature": 0, "seed": 42, "num_predict": 256 if advice else 192})
    answer = format_answer(raw, allow_guidance=advice)
    if advice:
        if _COMMAND_PATTERN.search(answer):
            answer = _WITHHELD_GUIDANCE
        if DISCLAIMER_TEXT not in answer:
            answer += f"\n\n{DISCLAIMER_TEXT}"
    return answer

"""Small, dependency-free schemas for the two model response contracts."""

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "Brief objective actions in temporal order."},
        "unusual_flagged": {"type": "boolean"},
        "unusual_note": {"type": "string", "description": "Visible unusual event; empty when not flagged."},
        "guidance_assessment": {"type": "string", "description": "Hedged observation grounded in visible evidence."},
        "guidance_suggestion": {"type": "string", "description": "Specific soft suggestion, or explain insufficient evidence. No commands or invented distances."},
        "guidance_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["description", "unusual_flagged", "unusual_note", "guidance_assessment", "guidance_suggestion", "guidance_confidence"],
    "additionalProperties": False,
}

FACTUAL_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

ADVICE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "guidance": {"type": "string", "description": "Hedged, specific suggestion based on visible evidence. No commands or invented distances."},
    },
    "required": ["answer", "guidance"],
    "additionalProperties": False,
}


def validate_response(data: object, schema: dict) -> dict:
    """Validate our flat schemas; do not pretend to implement full JSON Schema."""
    if not isinstance(data, dict):
        raise ValueError("Model response must be a JSON object")
    required = set(schema["required"])
    if not required.issubset(data):
        raise ValueError(f"Missing response fields: {sorted(required - data.keys())}")
    properties = schema["properties"]
    if set(data) - set(properties):
        raise ValueError("Model response has unexpected fields")
    for key, value in data.items():
        rule = properties[key]
        expected_type = str if rule["type"] == "string" else bool
        if type(value) is not expected_type:
            raise ValueError(f"Invalid type for response field: {key}")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"Invalid value for response field: {key}")
    for key in ("description", "answer"):
        if key in data and not data[key].strip():
            raise ValueError(f"Empty response field: {key}")
    if data.get("unusual_flagged") and not data["unusual_note"].strip():
        raise ValueError("Flagged unusual event requires an explanation")
    if data.get("unusual_flagged") is False and data["unusual_note"].strip():
        raise ValueError("Unflagged unusual event must have an empty note")
    return data

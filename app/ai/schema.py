from __future__ import annotations


INTENT_NAMES = [
    "ledger.create",
    "ledger.query",
    "todo.create",
    "todo.complete",
    "todo.query",
    "knowledge.capture_text",
    "knowledge.capture_link",
    "export.ledger_excel",
    "clarify",
    "unknown",
]


INTENT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "confidence", "fields", "missing_fields", "reply"],
    "properties": {
        "intent": {"type": "string", "enum": INTENT_NAMES},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "fields": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entry_type": {"type": ["string", "null"]},
                "amount": {"type": ["number", "null"]},
                "currency": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
                "note": {"type": ["string", "null"]},
                "occurred_at": {"type": ["string", "null"]},
                "todo_title": {"type": ["string", "null"]},
                "due_at": {"type": ["string", "null"]},
                "recurrence_rule": {"type": ["string", "null"]},
                "priority": {"type": ["string", "null"]},
                "content": {"type": ["string", "null"]},
                "source_url": {"type": ["string", "null"]},
                "query_range": {"type": ["string", "null"]},
                "query_category": {"type": ["string", "null"]},
            },
        },
        "missing_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reply": {"type": "string"},
    },
}


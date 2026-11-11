"""Conversation state & decisions. The BACKEND decides — never the AI.

The AI proposes values and a draft reply (AgentOutput). This module:
  1. validates every proposed value (name / domicile / vehicle),
  2. updates the conversation state (with history of corrections),
  3. decides the next field to ask (one at a time, max N asks per field),
  4. decides when to hand over to humans and which message to send,
  5. blocks replies that mention prices/promos not found in approved knowledge.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.adapters.ai.base import AgentOutput, KnowledgeContext
from app.adapters.ai.text_match import best_match, normalize, title_case
from app.core import texts
from app.models.enums import QUALIFICATION_ORDER, FieldStatus, HandoverReason

TITLES = re.compile(r"^(bapak|ibu|pak|bu|kak|mas|mbak|mba|bang|sdr|sdri)\.?\s+", re.IGNORECASE)
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,59}$")
NOT_A_NAME = {
    "ya",
    "iya",
    "ok",
    "oke",
    "halo",
    "hai",
    "tidak",
    "gak",
    "ga",
    "nggak",
    "test",
    "tes",
    "customer",
    "mitsubishi",
    "dipo",
    "sales",
    "admin",
    "rahasia",
    "anonim",
    "unknown",
    "-",
}
DOMICILE_RE = re.compile(r"^[A-Za-z][A-Za-z .\-]{1,59}$")
NOT_A_PLACE = {
    "rumah",
    "sini",
    "sana",
    "situ",
    "kantor",
    "indonesia",
    "rahasia",
    "jauh",
    "dekat",
    "ya",
    "iya",
    "ok",
    "oke",
    "tidak",
    "gak",
    "ga",
    "belum tahu",
    "belum tau",
    "nanti",
}
DOMICILE_PREFIX = re.compile(r"^(di|dari|dr|daerah|domisili|tinggal di)\s+", re.IGNORECASE)

# Money / percentage / tenor mentions that must be backed by approved knowledge.
MONEY_RE = re.compile(
    r"rp\.?\s?(\d[\d.,]*)(?:\s?(juta|jt|ribu|rb|miliar|m)\b)?"
    r"|(\d[\d.,]*)\s?((?:juta|jt|ribu|rb|miliar|persen)\b|%)",
    re.IGNORECASE,
)
MULTIPLIER = {"juta": 10**6, "jt": 10**6, "ribu": 10**3, "rb": 10**3, "miliar": 10**9, "m": 10**9}


# --------------------------------------------------------------------- validation
def validate_name(value: str) -> str | None:
    value = TITLES.sub("", " ".join(value.split())).strip(" .,")
    if not value or not NAME_RE.match(value) or len(value.split()) > 4:
        return None
    if normalize(value) in NOT_A_NAME:
        return None
    return title_case(value)


def validate_domicile(value: str, city_catalog: dict[str, list[str]]) -> str | None:
    value = DOMICILE_PREFIX.sub("", " ".join(value.split())).strip(" .,")
    if not value or not DOMICILE_RE.match(value) or len(value.split()) > 5:
        return None
    if normalize(value) in NOT_A_PLACE:
        return None
    return best_match(value, city_catalog, threshold=0.85) or title_case(value)


def validate_vehicle(value: str, vehicle_catalog: dict[str, list[str]]) -> str | None:
    value = " ".join(value.split()).strip(" .,")
    if not value or len(value) > 100:
        return None
    if vehicle_catalog:
        # Only models that exist in the approved catalog are accepted.
        return best_match(value, vehicle_catalog)
    return title_case(value)


# --------------------------------------------------------------------- grounding guard
def _amounts(text: str) -> set[int]:
    found: set[int] = set()
    for m in MONEY_RE.finditer(text):
        number, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        unit = (unit or "").lower()
        if unit in ("%", "persen") or unit not in MULTIPLIER:
            digits = re.sub(r"[.,]", "", number)
            if digits:
                found.add(int(digits))
            continue
        normalized = number.replace(".", "").replace(",", ".")
        try:
            found.add(int(float(normalized) * MULTIPLIER[unit]))
        except ValueError:
            continue
    return found


def ungrounded_amounts(reply: str, knowledge: KnowledgeContext) -> set[int]:
    """Amounts in the reply that do not appear in approved knowledge."""
    allowed = _amounts(knowledge.text) | {
        int(d) for d in re.findall(r"\d+", re.sub(r"(?<=\d)[.,](?=\d{3})", "", knowledge.text))
    }
    return {a for a in _amounts(reply) if a not in allowed}


# --------------------------------------------------------------------- state helpers
def empty_fields() -> dict:
    return {
        f.value: {"status": FieldStatus.MISSING.value, "value": None, "asks": 0}
        for f in QUALIFICATION_ORDER
    }


def known_values(fields: dict) -> dict[str, str | None]:
    return {k: v.get("value") for k, v in fields.items()}


def missing_fields(fields: dict) -> list[str]:
    return [
        f.value for f in QUALIFICATION_ORDER if fields[f.value]["status"] == FieldStatus.MISSING
    ]


@dataclass
class Decision:
    fields: dict
    reply: str | None
    reply_source: str  # ai | ai+question | template | closing | human_handover | ai_unavailable
    asked_field: str | None
    handover_reason: str | None
    changes: list[dict] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)
    guard_blocked: set[int] = field(default_factory=set)

    def as_log(self) -> dict:
        return {
            "reply_source": self.reply_source,
            "asked_field": self.asked_field,
            "handover_reason": self.handover_reason,
            "changes": self.changes,
            "rejected": self.rejected,
            "guard_blocked": sorted(self.guard_blocked),
        }


@dataclass
class DecisionInput:
    fields: dict
    output: AgentOutput | None  # None = AI failed
    knowledge: KnowledgeContext
    city_catalog: dict[str, list[str]]
    max_asks: int
    is_first_reply: bool
    consecutive_ai_failures: int
    messages: dict[str, str]  # closing / human / ai_unavailable templates (rendered later)


MAX_AI_FAILURES = 3


def decide(inp: DecisionInput) -> Decision:
    fields = {k: dict(v) for k, v in inp.fields.items()}
    out = inp.output
    changes: list[dict] = []
    rejected: dict[str, str] = {}
    newly_collected: set[str] = set()
    now = datetime.now(UTC).isoformat()

    # 1) Validate & merge proposed values. Empty = "no new info" (never erases).
    if out is not None:
        proposals = {
            "name": (out.customer_name, lambda v: validate_name(v)),
            "domicile": (out.domicile, lambda v: validate_domicile(v, inp.city_catalog)),
            "vehicle": (
                out.vehicle_model,
                lambda v: validate_vehicle(v, inp.knowledge.vehicle_catalog),
            ),
        }
        for name, (raw, validator) in proposals.items():
            raw = (raw or "").strip()
            if not raw:
                continue
            value = validator(raw)
            if value is None:
                if fields[name]["value"] is None:
                    rejected[name] = raw
                continue
            old = fields[name]["value"]
            if value != old:
                fields[name].update(status=FieldStatus.COLLECTED.value, value=value)
                newly_collected.add(name)
                changes.append(
                    {
                        "at": now,
                        "field": name,
                        "old": old,
                        "new": value,
                        "type": "correction" if old else "collected",
                    }
                )
        for name in out.declined_fields:
            if fields[name]["status"] == FieldStatus.MISSING.value:
                fields[name]["status"] = FieldStatus.DECLINED.value
                changes.append(
                    {"at": now, "field": name, "old": None, "new": None, "type": "declined"}
                )

    # 2) Don't keep pushing: a field asked max times without an answer is skipped.
    for name in missing_fields(fields):
        if fields[name]["asks"] >= inp.max_asks and name not in rejected:
            fields[name]["status"] = FieldStatus.DECLINED.value
            changes.append(
                {"at": now, "field": name, "old": None, "new": None, "type": "unanswered"}
            )
    # A rejected answer to a field already asked max times is also given up.
    for name in list(rejected):
        if (
            fields[name]["asks"] >= inp.max_asks
            and fields[name]["status"] == FieldStatus.MISSING.value
        ):
            fields[name]["status"] = FieldStatus.DECLINED.value
            changes.append(
                {"at": now, "field": name, "old": None, "new": None, "type": "unanswered"}
            )

    remaining = missing_fields(fields)
    next_field = remaining[0] if remaining else None
    base = Decision(fields, None, "", next_field, None, changes, rejected)

    # 3) Handover decisions (backend rules only).
    if out is None and inp.consecutive_ai_failures + 1 >= MAX_AI_FAILURES:
        base.reply, base.reply_source = inp.messages["ai_unavailable"], "ai_unavailable"
        base.handover_reason, base.asked_field = HandoverReason.AI_UNAVAILABLE, None
        return base
    if out is not None and out.intent == "request_human" and next_field is not None:
        base.reply, base.reply_source = inp.messages["human"], "human_handover"
        base.handover_reason, base.asked_field = HandoverReason.HUMAN_REQUESTED, None
        return base
    if next_field is None:
        all_collected = all(f["status"] == FieldStatus.COLLECTED.value for f in fields.values())
        base.reply, base.reply_source = inp.messages["closing"], "closing"
        base.handover_reason = (
            HandoverReason.QUALIFICATION_COMPLETE if all_collected else HandoverReason.PARTIAL_DATA
        )
        return base

    # 4) Choose the reply: AI draft when it is safe and consistent, else a template.
    blocked: set[int] = set()
    if out is not None and out.reply.strip():
        blocked = ungrounded_amounts(out.reply, inp.knowledge)
    base.guard_blocked = blocked
    ai_ok = out is not None and out.reply.strip() and not blocked and not rejected
    if ai_ok and out.asked_field == next_field:
        base.reply, base.reply_source = out.reply.strip(), "ai"
    elif ai_ok and out.asked_field == "none":
        base.reply = f"{out.reply.strip()} {texts.QUESTIONS[next_field]}"
        base.reply_source = "ai+question"
    else:
        parts: list[str] = []
        if inp.is_first_reply:
            parts.append(texts.GREETING)
        if blocked:
            parts.append(texts.NO_INFO.format(topic="harga/promo tersebut"))
        if "name" in newly_collected:
            parts.append(f"Salam kenal, Bapak/Ibu {fields['name']['value']}.")
        if next_field in rejected:
            examples = ", ".join(list(inp.knowledge.vehicle_catalog)[:3]) or "Xpander, Pajero Sport"
            parts.append(texts.REASK[next_field].format(examples=examples))
        else:
            parts.append(texts.QUESTIONS[next_field])
        base.reply, base.reply_source = " ".join(parts), "template"

    fields[next_field]["asks"] += 1
    return base

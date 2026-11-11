"""Deterministic rule-based "AI" for development and automated tests.

Free, offline and repeatable. It returns the SAME AgentOutput contract as the
real LLM providers, so the backend logic under test is identical. It is not as
smart as a real LLM: it recognises common Indonesian phrasing, informal words,
known city/vehicle aliases and small typos.
"""

import re

from app.adapters.ai.base import AgentOutput, AgentRequest, AIResult
from app.adapters.ai.text_match import find_mentions, normalize, title_case
from app.core import texts

HUMAN_RE = re.compile(
    r"\b(bicara|ngobrol|chat|hubungkan|sambungkan|telpon|telepon)\b.*\b(sales|orang|manusia|admin|cs)\b"
    r"|\b(minta|mau|tolong)\b.*\b(sales|admin|cs|manusia)\b"
    r"|\bdihubungi\b"
)
DECLINE_RE = re.compile(
    r"\b(rahasia|ga mau|gak mau|nggak mau|ngga mau|tidak mau|enggak mau|ogah|skip|"
    r"ga usah|gak usah|tidak usah|nanti aja|ntar aja|belum mau|privasi)\b"
)
GREETINGS = {
    "halo",
    "hallo",
    "hai",
    "hi",
    "hello",
    "pagi",
    "siang",
    "sore",
    "malam",
    "permisi",
    "assalamualaikum",
    "selamat pagi",
    "selamat siang",
    "selamat sore",
    "selamat malam",
    "halo kak",
    "halo min",
    "p",
    "ping",
}
TOPIC_PATTERNS = [
    ("promo", re.compile(r"\b(promo|diskon|potongan|cashback|hadiah)\b")),
    ("dp", re.compile(r"\b(dp|uang muka)\b")),
    ("installment", re.compile(r"\b(angsuran|cicilan|kredit|leasing|tenor)\b")),
    ("price", re.compile(r"\b(harga|harganya|price|berapaan|otr)\b")),
    (
        "dealer",
        re.compile(r"\b(alamat|lokasi|dealer|showroom|jam buka|buka jam|jam operasional)\b"),
    ),
    ("spec", re.compile(r"\b(spesifikasi|spek|mesin|cc|irit|konsumsi bbm|fitur)\b")),
]
NAME_TRIGGER = re.compile(
    r"\b(?:nama saya|nama aku|namaku|nama sy|panggil saja|panggil aja|saya|aku|sy|gue|gw)\s+"
    r"([a-z]+(?:\s+[a-z]+)?)"
)
NAME_STOPWORDS = {
    "mau",
    "ingin",
    "pengen",
    "pingin",
    "tanya",
    "nanya",
    "lagi",
    "cari",
    "nyari",
    "butuh",
    "minat",
    "tertarik",
    "dari",
    "di",
    "dr",
    "tinggal",
    "domisili",
    "sudah",
    "udah",
    "belum",
    "tidak",
    "ga",
    "gak",
    "nggak",
    "bukan",
    "juga",
    "sih",
    "aja",
    "saja",
    "ya",
    "iya",
    "ok",
    "oke",
    "punya",
    "lihat",
    "liat",
    "kerja",
    "orang",
    "asli",
    "dan",
    "yang",
    "the",
    "bisa",
    "masih",
    "sedang",
    "lg",
    "ada",
    "rencana",
    "pikir",
    "kira",
    "tau",
    "tahu",
    "nih",
    "mo",
    "kak",
    "pak",
    "bu",
    "mas",
    "mba",
    "mbak",
    "bang",
    "min",
    "admin",
    "sales",
    "lah",
    "kok",
    "baru",
    "sendiri",
    "nama",
    "namanya",
    "salah",
    "tapi",
    # informal abbreviations
    "mw",
    "tny",
    "pgn",
    "minta",
    "info",
    "tolong",
    "dong",
    "deh",
    "kasih",
    "ganti",
}
TITLES = {"pak", "bu", "bapak", "ibu", "kak", "mas", "mba", "mbak", "bang", "sdr", "sdri"}
DOMICILE_TRIGGER = re.compile(
    r"\b(?:domisili|tinggal di|tinggal|daerah|dari|dr|di|kota|kab|kabupaten)\s+"
    r"([a-z]+(?:\s+[a-z]+)?)"
)


def _latest_contact_text(req: AgentRequest) -> str:
    parts: list[str] = []
    for turn in reversed(req.history):
        if turn.role != "contact":
            break
        parts.append(turn.text)
    return "\n".join(reversed(parts))


NEGATIONS = {"bukan", "bkn", "selain"}


def _without_negated(text: str, mentions: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop mentions right after "bukan" ("saya di Binjai bukan Medan" -> Binjai)."""
    tokens = normalize(text).split()
    return [(p, n) for p, n in mentions if not (p > 0 and tokens[p - 1] in NEGATIONS)]


def _clean_name(raw: str) -> str | None:
    words = [w for w in normalize(raw).split() if w not in TITLES]
    kept: list[str] = []
    for word in words:
        if word in NAME_STOPWORDS or word.isdigit():
            break
        kept.append(word)
    if not kept or len(kept) > 3:
        return None
    return title_case(" ".join(kept))


def _is_greeting(text_n: str) -> bool:
    return text_n in GREETINGS or (len(text_n.split()) <= 2 and text_n.split()[0] in GREETINGS)


class MockAIProvider:
    name = "mock"
    model = "mock-rules-v2"

    async def run_turn(self, req: AgentRequest) -> AIResult:
        return AIResult(output=self.decide(req), provider=self.name, model=self.model, latency_ms=0)

    def decide(self, req: AgentRequest) -> AgentOutput:
        text = _latest_contact_text(req)
        text_n = normalize(text)
        tokens = text_n.split()
        known = {k: v for k, v in req.known.items()}
        newly: set[str] = set()
        last_asked = req.last_asked_field

        vehicles = _without_negated(text, find_mentions(text, req.knowledge.vehicle_catalog))
        cities = _without_negated(text, find_mentions(text, req.city_catalog))
        vehicle_tokens = {normalize(v) for _, v in vehicles}

        # --- vehicle (last mention wins => handles corrections) ---
        if vehicles:
            value = vehicles[-1][1]
            if value != known.get("vehicle"):
                newly.add("vehicle")
            known["vehicle"] = value

        # --- domicile ---
        domicile = None
        if cities:
            domicile = cities[-1][1]
        else:
            matches = list(DOMICILE_TRIGGER.finditer(text_n))
            match = matches[-1] if matches else None
            if match and (last_asked == "domicile" or re.search(r"domisili|tinggal", text_n)):
                candidate = _clean_name(match.group(1))
                if candidate and normalize(candidate) not in vehicle_tokens:
                    domicile = candidate
            elif (
                last_asked == "domicile"
                and 0 < len(tokens) <= 4
                and not vehicles
                and not DECLINE_RE.search(text_n)
                and not _is_greeting(text_n)
                and "?" not in text
            ):
                domicile = _clean_name(text_n)
        if domicile:
            if domicile != known.get("domicile"):
                newly.add("domicile")
            known["domicile"] = domicile

        # --- name ---
        name = None
        if "nama" in text_n and "bukan" in text_n and "tapi" in text_n:
            name = _clean_name(text_n.split("tapi", 1)[1])
        if not name:
            for m in NAME_TRIGGER.finditer(text_n):
                candidate = _clean_name(m.group(1))
                if candidate and normalize(candidate) not in vehicle_tokens | {
                    normalize(c) for _, c in cities
                }:
                    name = candidate
                    break
        if (
            not name
            and last_asked == "name"
            and 0 < len(tokens) <= 3
            and not vehicles
            and not cities
            and not DECLINE_RE.search(text_n)
            and not _is_greeting(text_n)
            and "?" not in text
        ):
            name = _clean_name(text_n)
        if name:
            if name != known.get("name"):
                newly.add("name")
            known["name"] = name

        # --- intent ---
        intent = "provide_info" if newly else "other"
        topic = next((t for t, rx in TOPIC_PATTERNS if rx.search(text_n)), None)
        if topic or "?" in text:
            intent = "question"
        if not newly and not topic and _is_greeting(text_n):
            intent = "greeting"
        if HUMAN_RE.search(text_n):
            intent = "request_human"

        declined: list[str] = []
        if DECLINE_RE.search(text_n) and last_asked and not known.get(last_asked):
            declined.append(last_asked)

        # --- reply ---
        parts: list[str] = []
        if req.is_first_reply:
            parts.append(texts.GREETING)
        if intent == "question":
            parts.append(self._answer(topic or "faq", req, known.get("vehicle")))
        if "name" in newly and known.get("name"):
            parts.append(f"Salam kenal, Bapak/Ibu {known['name']}.")
        elif newly and not req.is_first_reply:
            parts.append(texts.with_name(known.get("name")))

        asked = "none"
        for field in req.missing_fields:
            if field in declined or known.get(field):
                continue
            asked = field
            break
        if asked != "none":
            parts.append(texts.QUESTIONS[asked])
        elif not parts:
            parts.append(texts.THANKS)

        return AgentOutput(
            customer_name=known.get("name") or "",
            domicile=known.get("domicile") or "",
            vehicle_model=known.get("vehicle") or "",
            declined_fields=declined,  # type: ignore[arg-type]
            intent=intent,  # type: ignore[arg-type]
            asked_field=asked,  # type: ignore[arg-type]
            reply=" ".join(parts),
        )

    @staticmethod
    def _answer(topic: str, req: AgentRequest, vehicle: str | None) -> str:
        entries = [e for e in req.knowledge.entries if e[0] == topic]
        if vehicle:
            specific = [e for e in entries if vehicle.lower() in (e[1] + e[2]).lower()]
            entries = specific or entries
        if entries:
            _, title, content = entries[0]
            return f"Untuk {title}: {content}"
        return texts.NO_INFO.format(topic=texts.TOPIC_LABELS.get(topic, topic))

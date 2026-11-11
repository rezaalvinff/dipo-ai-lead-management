"""Small, dependency-free text helpers: normalization and typo-tolerant matching."""

import re
import unicodedata
from difflib import SequenceMatcher

_NON_WORD = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")

# Common Indonesian cities/regencies + informal spellings, used to recognise a
# domicile inside free text ("saya budi dari bks"). Not exhaustive on purpose:
# any short answer to the domicile question is accepted too.
CITY_ALIASES: dict[str, list[str]] = {
    "Jakarta": ["jakarta", "jkt", "dki"],
    "Jakarta Selatan": ["jakarta selatan", "jaksel", "jkt selatan"],
    "Jakarta Barat": ["jakarta barat", "jakbar"],
    "Jakarta Timur": ["jakarta timur", "jaktim"],
    "Jakarta Utara": ["jakarta utara", "jakut"],
    "Jakarta Pusat": ["jakarta pusat", "jakpus"],
    "Bekasi": ["bekasi", "bks"],
    "Depok": ["depok"],
    "Bogor": ["bogor"],
    "Tangerang": ["tangerang", "tng"],
    "Tangerang Selatan": ["tangerang selatan", "tangsel"],
    "Bandung": ["bandung", "bdg"],
    "Surabaya": ["surabaya", "sby"],
    "Semarang": ["semarang", "smg"],
    "Yogyakarta": ["yogyakarta", "jogja", "yogya", "jogjakarta"],
    "Medan": ["medan", "mdn"],
    "Binjai": ["binjai"],
    "Deli Serdang": ["deli serdang"],
    "Pematangsiantar": ["pematangsiantar", "siantar"],
    "Palembang": ["palembang", "plg"],
    "Pekanbaru": ["pekanbaru"],
    "Padang": ["padang"],
    "Makassar": ["makassar", "makasar", "mks"],
    "Denpasar": ["denpasar", "dps"],
    "Balikpapan": ["balikpapan", "bpn"],
    "Samarinda": ["samarinda"],
    "Pontianak": ["pontianak"],
    "Banjarmasin": ["banjarmasin"],
    "Malang": ["malang"],
    "Solo": ["solo", "surakarta"],
    "Cirebon": ["cirebon"],
    "Karawang": ["karawang"],
    "Cikarang": ["cikarang"],
    "Serang": ["serang"],
    "Lampung": ["lampung", "bandar lampung"],
    "Batam": ["batam"],
    "Manado": ["manado"],
    "Jambi": ["jambi"],
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = _NON_WORD.sub(" ", text.lower())
    return _SPACES.sub(" ", text).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _ngrams(tokens: list[str], max_n: int = 3) -> list[tuple[int, str]]:
    grams = []
    for n in range(max_n, 0, -1):
        for i in range(len(tokens) - n + 1):
            grams.append((i, " ".join(tokens[i : i + n])))
    return grams


def find_mentions(
    text: str, catalog: dict[str, list[str]], *, threshold: float = 0.84
) -> list[tuple[int, str]]:
    """Return (token_position, canonical_name) for every catalog entry found in text.

    Exact alias matches win; otherwise a fuzzy match (typos) above ``threshold``.
    Longer aliases are preferred ("pajero sport" over "pajero").
    """
    tokens = normalize(text).split()
    found: dict[str, int] = {}
    used: set[int] = set()
    # Longest n-grams first so "xpander cross" beats "xpander".
    for pos, gram in _ngrams(tokens):
        span = set(range(pos, pos + len(gram.split())))
        if span & used:
            continue
        best_name, best_score = None, 0.0
        for canonical, aliases in catalog.items():
            for alias in [canonical, *aliases]:
                alias_n = normalize(alias)
                if not alias_n or len(alias_n.split()) != len(gram.split()):
                    continue
                if gram == alias_n:
                    score = 1.0
                elif len(alias_n) >= 5 and len(gram) >= 4:
                    score = similarity(gram, alias_n)
                else:
                    score = 0.0
                if score > best_score:
                    best_name, best_score = canonical, score
        if best_name and best_score >= threshold:
            if best_name not in found:
                found[best_name] = pos
            else:
                found[best_name] = max(found[best_name], pos)
            used |= span
    return sorted(((p, n) for n, p in found.items()), key=lambda x: x[0])


def best_match(value: str, catalog: dict[str, list[str]], *, threshold: float = 0.8) -> str | None:
    """Match a whole value (e.g. the AI's "vehicle_model") to a canonical name."""
    value_n = normalize(value)
    if not value_n:
        return None
    best_name, best_score = None, 0.0
    for canonical, aliases in catalog.items():
        for alias in [canonical, *aliases]:
            alias_n = normalize(alias)
            if not alias_n:
                continue
            score = 1.0 if value_n == alias_n else similarity(value_n, alias_n)
            if score > best_score:
                best_name, best_score = canonical, score
    if best_score >= threshold:
        return best_name
    # Mentions inside a longer value, e.g. "mitsubishi xpander ultimate".
    mentions = find_mentions(value, catalog)
    return mentions[-1][1] if mentions else None


def title_case(value: str) -> str:
    return " ".join(w[:1].upper() + w[1:].lower() for w in value.split())

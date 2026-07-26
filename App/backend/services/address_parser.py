import re
import uuid
from difflib import SequenceMatcher

from core.schemas import AddressCandidate

LOGRADOURO_RE = re.compile(
    r"(?i)(?<![a-zà-ú])(rua|r\.|avenida|av\.?|travessa|tv\.?|alameda|al\.?|"
    r"rodovia|rod\.?|estrada|estr\.?|pra[çc]a|p[çc]a\.?|largo|viela|via|linha)(?![a-zà-ú])"
)
CEP_RE = re.compile(r"\b(\d{5})-?(\d{3})\b")
NUMERO_RE = re.compile(r"(?i)(?:,\s*|\bn[ºo°.]?\s*)(\d{1,5})\b")
CONTEXTO_RE = re.compile(
    r"(?i)\b(bairro|cidade|cep|munic[ií]pio|distrito|jardim|jd\.?|vila|centro|"
    r"parque|conjunto|residencial|quadra|lote)\b"
    r"|[-/,]\s?(AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO)\b"
)
RUIDO_RE = re.compile(r"[|_~•■□®°]+")
THRESHOLD = 0.3


def _score(text: str) -> float:
    score = 0.0
    if LOGRADOURO_RE.search(text):
        score += 0.4
    if CEP_RE.search(text):
        score += 0.3
    if NUMERO_RE.search(text):
        score += 0.15
    if CONTEXTO_RE.search(text):
        score += 0.15
    return round(score, 2)


def _clean(text: str) -> str:
    text = RUIDO_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-")
    text = CEP_RE.sub(lambda m: f"{m.group(1)}-{m.group(2)}", text)
    return text


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def extract_address_candidates(text: str, pair_lines: bool = True) -> list[AddressCandidate]:
    """pair_lines junta linhas adjacentes (útil no OCR, onde o endereço pode
    quebrar em duas linhas); em dados tabulares cada linha já é um registro."""
    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if len(ln) >= 6]

    windows: list[str] = []
    windows.extend(lines)
    if pair_lines:
        for i in range(len(lines) - 1):
            windows.append(f"{lines[i]}, {lines[i + 1]}")

    scored = []
    for raw in windows:
        s = _score(raw)
        if s >= THRESHOLD:
            cleaned = _clean(raw)
            if len(cleaned) >= 8:
                scored.append((s, raw, cleaned))
    scored.sort(key=lambda item: item[0], reverse=True)

    candidates: list[AddressCandidate] = []
    for s, raw, cleaned in scored:
        if any(_similar(cleaned, c.cleaned) > 0.85 for c in candidates):
            continue
        candidates.append(AddressCandidate(
            id=uuid.uuid4().hex[:8],
            raw_text=raw,
            cleaned=cleaned,
            confidence=min(s, 1.0),
        ))
    return candidates


def merge_candidates(*groups: list[AddressCandidate]) -> list[AddressCandidate]:
    merged: list[AddressCandidate] = []
    for group in groups:
        for cand in group:
            if any(_similar(cand.cleaned, c.cleaned) > 0.85 for c in merged):
                continue
            merged.append(cand)
    return merged

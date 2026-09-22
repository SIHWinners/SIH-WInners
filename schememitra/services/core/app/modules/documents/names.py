"""Name normalisation and loose identity matching (spec §9.2, claim C11).

"Shri Ramesh S/O Late Kanaram" on a caste certificate and "RAMESH KANARAM MEGHWAL" on a
passbook are the same person. We strip honorifics and relation words, transliterate Indic
scripts to Latin, compare tokens order-insensitively with Jaro-Winkler (plus a phonetic key for
spelling drift) and require at least one hard anchor (DOB, Aadhaar last-4 or father's name)."""

import re
import unicodedata
from dataclasses import dataclass, field

from indic_transliteration import sanscript
from rapidfuzz.distance import JaroWinkler

MATCH_THRESHOLD = 0.88

HONORIFICS = {
    "shri", "shree", "sri", "sree", "smt", "shrimati", "srimati", "kum", "kumari", "km", "sushri", "su",
    "mr", "mrs", "ms", "miss", "dr", "late", "lt", "sh", "shrimaan", "thiru", "thirumathi", "selvi",
    "md", "mohd", "janab", "begum",
}
RELATIONS = re.compile(r"\b(?:s|d|w|c)\s*/\s*o\b|\b(?:son|daughter|wife|care)\s+of\b", re.IGNORECASE)

_SCRIPTS = [
    ((0x0900, 0x097F), sanscript.DEVANAGARI), ((0x0980, 0x09FF), sanscript.BENGALI),
    ((0x0A00, 0x0A7F), sanscript.GURMUKHI), ((0x0A80, 0x0AFF), sanscript.GUJARATI),
    ((0x0B00, 0x0B7F), sanscript.ORIYA), ((0x0B80, 0x0BFF), sanscript.TAMIL),
    ((0x0C00, 0x0C7F), sanscript.TELUGU), ((0x0C80, 0x0CFF), sanscript.KANNADA),
    ((0x0D00, 0x0D7F), sanscript.MALAYALAM),
]


def _script_of(text: str) -> str | None:
    for ch in text:
        cp = ord(ch)
        for (lo, hi), scheme in _SCRIPTS:
            if lo <= cp <= hi:
                return scheme
    return None


def to_latin(text: str) -> tuple[str, bool]:
    scheme = _script_of(text)
    if scheme is None:
        return text, False
    latin = sanscript.transliterate(text, scheme, sanscript.ITRANS)
    # Schwa deletion: names are written "Ramesh", not "Ramesha", so drop a word-final inherent "a".
    latin = re.sub(r"(?<=[^aeiouAEIOU\s])a\b", "", latin)
    return latin, True


@dataclass
class ParsedName:
    raw: str
    tokens: list[str]
    relation_tokens: list[str]
    reasons: set[str] = field(default_factory=set)

    @property
    def normalized(self) -> str:
        return " ".join(self.tokens)


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower().replace("~n", "n").replace(".n", "n").replace(".m", "m").replace(".h", "h")
    text = re.sub(r"(aa|ii|uu|ee|oo)", lambda m: m.group(0)[0], text)
    return re.sub(r"[^a-z\s/]", " ", text)


def parse_name(raw: str) -> ParsedName:
    reasons: set[str] = set()
    latin, transliterated = to_latin(raw)
    if transliterated:
        reasons.add("transliterated")
    text = _ascii_fold(latin)
    relation_tokens: list[str] = []
    split = RELATIONS.split(text, maxsplit=1)
    if len(split) == 2:
        reasons.add("relation_removed")
        text, relation = split
        relation_tokens = [w for w in relation.split() if w not in HONORIFICS and len(w) > 1]
    words = text.replace("/", " ").split()
    tokens = [w for w in words if w not in HONORIFICS and len(w) > 1]
    if len(tokens) != len([w for w in words if len(w) > 1]):
        reasons.add("honorific_removed")
    if any(w in HONORIFICS for w in _ascii_fold(latin).split()):
        reasons.add("honorific_removed")
    return ParsedName(raw, tokens, relation_tokens, reasons)


def normalize_name(raw: str) -> str:
    return parse_name(raw).normalized


def phonetic_key(token: str) -> str:
    """Double-Metaphone-style key tuned for Indian names written in Latin script."""
    t = token.lower()
    for a, b in (("ph", "f"), ("bh", "b"), ("dh", "d"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("chh", "c"),
                 ("ch", "c"), ("sh", "s"), ("jh", "j"), ("v", "w"), ("z", "j"), ("q", "k"), ("x", "ks"), ("y", "i")):
        t = t.replace(a, b)
    t = t.rstrip("h")
    t = re.sub(r"(.)\1+", r"\1", t)
    return t[:1] + re.sub(r"[aeiou]", "", t[1:])


def _token_similarity(a: str, b: str) -> float:
    direct = JaroWinkler.similarity(a, b)
    phonetic = 1.0 if phonetic_key(a) == phonetic_key(b) else JaroWinkler.similarity(phonetic_key(a), phonetic_key(b))
    return max(direct, 0.97 * phonetic)


def token_score(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return sum(max(_token_similarity(s, t) for t in long_) for s in short) / len(short)


@dataclass
class MatchResult:
    score: float
    matched: bool
    reasons: list[str]
    left: str
    right: str


def match_names(
    left_raw: str,
    right_raw: str,
    *,
    dob_left: str | None = None,
    dob_right: str | None = None,
    aadhaar_last4_left: str | None = None,
    aadhaar_last4_right: str | None = None,
    father_left: str | None = None,
    father_right: str | None = None,
) -> MatchResult:
    left, right = parse_name(left_raw), parse_name(right_raw)
    reasons = left.reasons | right.reasons
    score = token_score(left.tokens, right.tokens)
    if left.tokens and right.tokens and left.tokens != right.tokens and sorted(left.tokens) == sorted(right.tokens):
        reasons.add("token_order")

    anchors = set()
    if dob_left and dob_right and dob_left == dob_right:
        anchors.add("anchor_dob")
    if aadhaar_last4_left and aadhaar_last4_right and aadhaar_last4_left == aadhaar_last4_right:
        anchors.add("anchor_aadhaar")
    # Father's name: explicit fields, or the S/O part of one document appearing in the other's name.
    fathers = [parse_name(f).tokens for f in (father_left, father_right) if f]
    relation_sources = [left.relation_tokens, right.relation_tokens, *fathers]
    for rel in relation_sources:
        for other in (left.tokens, right.tokens):
            if rel and other is not rel and token_score(rel, other) >= MATCH_THRESHOLD and set(rel) - set(left.tokens if other is right.tokens else right.tokens):
                anchors.add("anchor_father")
    if len(fathers) == 2 and token_score(fathers[0], fathers[1]) >= MATCH_THRESHOLD:
        anchors.add("anchor_father")
    if not anchors:
        reasons.add("no_anchor")
    reasons |= anchors
    matched = score >= MATCH_THRESHOLD and bool(anchors)
    order = ["honorific_removed", "relation_removed", "token_order", "transliterated", "anchor_dob", "anchor_aadhaar",
             "anchor_father", "no_anchor"]
    return MatchResult(round(score, 3), matched, [r for r in order if r in reasons], left.normalized, right.normalized)

"""Text normalisation shared by the number parser and the slot extractor.

Speech transcripts arrive in native script (Bhashini, Whisper) or romanised Hinglish
(typed). Normalising both sides of every lexicon lookup the same way makes matching
robust to the spelling variation that is normal in Indian languages."""

import re
import unicodedata
from dataclasses import dataclass

# Nukta, chandrabindu→anusvara, ZWJ/ZWNJ: spelling variants that should compare equal.
_NUKTA = dict.fromkeys(map(ord, "़়਼઼଼಼"), None)
_ZW = dict.fromkeys(map(ord, "‌‍­"), None)
_CHANDRABINDU = {ord("ँ"): "ं", ord("ঁ"): "ং", ord("ઁ"): "ં", ord("ଁ"): "ଂ"}
_WORD = re.compile(r"[^\s,;:!?।॥()\[\]{}\"'“”‘’/|…۔،؟]+")
_LATIN = re.compile(r"[a-z]")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = text.translate(_NUKTA).translate(_ZW).translate(_CHANDRABINDU)
    # Unicode decimal digits in any script → ASCII (०-९, ૦-૯, ০-৯, ...).
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)


def roman_key(token: str) -> str:
    """Loose key for romanised words: 'pachaas', 'pachas' and 'pachass' share one key."""
    t = token.lower().replace("w", "v").replace("z", "j").replace("ph", "f").replace("ee", "i").replace("oo", "u")
    return re.sub(r"(.)\1+", r"\1", t)


def is_latin(token: str) -> bool:
    return bool(_LATIN.search(token))


def key(token: str) -> str:
    return roman_key(token) if is_latin(token) else token


@dataclass(frozen=True)
class Token:
    text: str  # normalised surface form
    start: int  # char offsets into the normalised string
    end: int


def tokenize(text: str) -> tuple[str, list[Token]]:
    norm = normalise(text)
    # Indian digit grouping 1,20,000 and currency glued to digits (₹60,000, rs.5000).
    norm = re.sub(r"(?<=\d),(?=\d)", "", norm)
    norm = re.sub(r"(₹|rs\.?|inr)(?=\d)", r"\1 ", norm)
    tokens: list[Token] = []
    for m in _WORD.finditer(norm):
        piece = m.group(0).rstrip(".")  # sentence full stop, but keep 2.5
        if piece:
            tokens.append(Token(piece, m.start(), m.start() + len(piece)))
    return norm, tokens


# Clause boundaries scope negation and money-to-slot assignment.
CLAUSE_SPLIT = re.compile(
    r"[;।॥!?،۔\n]+|(?<!\d)[.,]|[.,](?!\d)|\s(?:and|aur|or|ane|ani|mattu|arrum|mariyu|ebong|evam|और|अणि|आणि|એને|અને|ও|এবং|আৰু|மற்றும்|మరియు|ಮತ್ತು|ഒപ്പം|ଏବଂ|ਅਤੇ|اور)\s"
)


def clauses(text: str) -> list[str]:
    norm = re.sub(r"(?<=\d),(?=\d)", "", normalise(text))
    return [c.strip() for c in CLAUSE_SPLIT.split(norm) if c and c.strip()]

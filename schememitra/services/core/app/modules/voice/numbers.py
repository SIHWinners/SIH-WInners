"""Indian number and amount parser (spec §9.1): "dedh lakh", "2.5 lakh", "pachas hazaar",
"એક લાખ વીસ હજાર", "₹1,20,000", "sixty thousand". Runs before any LLM and overrides it.

Coverage (ADR-018): digits in every Indian script everywhere; unit words (hundred,
thousand, lakh, crore), fraction words (dedh, dhai, sava, saadhe, paune) and English
words in all 13 languages; full 0–99 number words for Hindi (Devanagari + romanised),
Urdu (via romanised Hindi and Urdu 0–10 + tens) and Gujarati; 0–10 plus tens for the
other languages. Speech engines output digits for most larger numbers, so the unit words
carry most of the load."""

from dataclasses import dataclass
from fractions import Fraction
from functools import cache

from app.modules.voice.text import Token, is_latin, key, normalise, tokenize

HINDI_DEVANAGARI = (
    "शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
    "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
    "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस "
    "सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
    "इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
    "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी "
    "अट्ठासी नवासी नब्बे इक्यानबे बानबे तिरानबे चौरानबे पचानबे छियानबे सत्तानबे अट्ठानबे निन्यानबे"
).split()
HINDI_ROMAN = (
    "shunya ek do teen char panch chhah saat aath nau das gyarah barah terah chaudah pandrah solah satrah "
    "atharah unnis bees ikkis bais teis chaubis pachchis chhabbis sattais atthais untis tees ikattis battis "
    "taintis chauntis paintis chhattis saintis adtis untalis chalis iktalis bayalis taintalis chavalis "
    "paintalis chhiyalis saintalis adtalis unchas pachas ikyavan bavan tirpan chauvan pachpan chhappan "
    "sattavan atthavan unsath saath iksath basath tirsath chaunsath painsath chhiyasath sadsath adsath "
    "unhattar sattar ikhattar bahattar tihattar chauhattar pachhattar chhihattar sathattar athhattar unasi "
    "assi ikyasi bayasi tirasi chaurasi pachasi chhiyasi sattasi atthasi navasi nabbe ikyanave banave "
    "tiranave chauranave pachanave chhiyanave sattanave atthanave ninyanave"
).split()
HINDI_VARIANTS = {"छः": 6, "छ": 6, "पांच": 5, "तेंतीस": 33, "चौतीस": 34, "इकत्तीस": 31, "उन्नासी": 79,
                  "chhe": 6, "che": 6, "chaar": 4, "paanch": 5, "athara": 18, "pachaas": 50, "sath": 60,
                  "chalees": 40, "assee": 80, "nabbe": 90, "pachees": 25, "pacchis": 25}
GUJARATI = (
    "શૂન્ય એક બે ત્રણ ચાર પાંચ છ સાત આઠ નવ દસ અગિયાર બાર તેર ચૌદ પંદર સોળ સત્તર અઢાર ઓગણીસ વીસ એકવીસ "
    "બાવીસ ત્રેવીસ ચોવીસ પચ્ચીસ છવ્વીસ સત્તાવીસ અઠ્ઠાવીસ ઓગણત્રીસ ત્રીસ એકત્રીસ બત્રીસ તેત્રીસ ચોત્રીસ "
    "પાંત્રીસ છત્રીસ સાડત્રીસ આડત્રીસ ઓગણચાલીસ ચાલીસ એકતાલીસ બેતાલીસ તેતાલીસ ચુંમાલીસ પિસ્તાલીસ છેતાલીસ "
    "સુડતાલીસ અડતાલીસ ઓગણપચાસ પચાસ એકાવન બાવન ત્રેપન ચોપન પંચાવન છપ્પન સત્તાવન અઠ્ઠાવન ઓગણસાઠ સાઠ "
    "એકસઠ બાસઠ ત્રેસઠ ચોસઠ પાંસઠ છાસઠ સડસઠ અડસઠ અગણોસિત્તેર સિત્તેર એકોતેર બોતેર તોતેર ચુમોતેર "
    "પંચોતેર છોતેર સિત્યોતેર ઇઠ્યોતેર ઓગણાએંસી એંસી એક્યાસી બ્યાસી ત્યાસી ચોર્યાસી પંચ્યાસી છ્યાસી "
    "સિત્યાસી અઠ્યાસી નેવ્યાસી નેવું એકાણું બાણું ત્રાણું ચોરાણું પંચાણું છન્નું સત્તાણું અઠ્ઠાણું નવ્વાણું"
).split()
GUJARATI_VARIANTS = {"ચુમ્માલીસ": 44, "દશ": 10, "અગીયાર": 11, "વિસ": 20, "ત્રીસ": 30, "પચીસ": 25}

# 0–10 then tens 20..90 (index 11..18) for languages without a full table here.
SMALL: dict[str, str] = {
    "mr": "शून्य एक दोन तीन चार पाच सहा सात आठ नऊ दहा वीस तीस चाळीस पन्नास साठ सत्तर ऐंशी नव्वद",
    "bn": "শূন্য এক দুই তিন চার পাঁচ ছয় সাত আট নয় দশ বিশ ত্রিশ চল্লিশ পঞ্চাশ ষাট সত্তর আশি নব্বই",
    "as": "শূন্য এক দুই তিনি চাৰি পাঁচ ছয় সাত আঠ ন দহ বিশ ত্ৰিশ চল্লিশ পঞ্চাশ ষাঠি সত্তৰ আশী নব্বৈ",
    "ta": "பூஜ்ஜியம் ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது பத்து இருபது முப்பது நாற்பது ஐம்பது அறுபது எழுபது எண்பது தொண்ணூறு",
    "te": "సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు ఆరు ఏడు ఎనిమిది తొమ్మిది పది ఇరవై ముప్పై నలభై యాభై అరవై డెబ్బై ఎనభై తొంభై",
    "kn": "ಸೊನ್ನೆ ಒಂದು ಎರಡು ಮೂರು ನಾಲ್ಕು ಐದು ಆರು ಏಳು ಎಂಟು ಒಂಬತ್ತು ಹತ್ತು ಇಪ್ಪತ್ತು ಮೂವತ್ತು ನಲವತ್ತು ಐವತ್ತು ಅರವತ್ತು ಎಪ್ಪತ್ತು ಎಂಬತ್ತು ತೊಂಬತ್ತು",
    "ml": "പൂജ്യം ഒന്ന് രണ്ട് മൂന്ന് നാല് അഞ്ച് ആറ് ഏഴ് എട്ട് ഒൻപത് പത്ത് ഇരുപത് മുപ്പത് നാൽപത് അമ്പത് അറുപത് എഴുപത് എൺപത് തൊണ്ണൂറ്",
    "or": "ଶୂନ ଏକ ଦୁଇ ତିନି ଚାରି ପାଞ୍ଚ ଛଅ ସାତ ଆଠ ନଅ ଦଶ କୋଡ଼ିଏ ତିରିଶ ଚାଳିଶ ପଚାଶ ଷାଠିଏ ସତୁରୀ ଅଶୀ ନବେ",
    "pa": "ਸਿਫ਼ਰ ਇੱਕ ਦੋ ਤਿੰਨ ਚਾਰ ਪੰਜ ਛੇ ਸੱਤ ਅੱਠ ਨੌਂ ਦਸ ਵੀਹ ਤੀਹ ਚਾਲੀ ਪੰਜਾਹ ਸੱਠ ਸੱਤਰ ਅੱਸੀ ਨੱਬੇ",
    "ur": "صفر ایک دو تین چار پانچ چھ سات آٹھ نو دس بیس تیس چالیس پچاس ساٹھ ستر اسی نوے",
}
ENGLISH = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
           "sixteen seventeen eighteen nineteen").split()
ENGLISH_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}

UNITS: dict[int, list[str]] = {
    100: ["hundred", "sau", "सौ", "शंभर", "سو", "સો", "শ", "শত", "நூறு", "వంద", "నూరు", "ನೂರು", "നൂറ്", "ଶହ", "ਸੌ"],
    1000: ["thousand", "k", "hazar", "hazaar", "hajar", "hajaar", "हज़ार", "हजार", "ہزار", "હજાર", "হাজার", "হাজাৰ",
           "ஆயிரம்", "వేయి", "వెయ్యి", "వేల", "ಸಾವಿರ", "ആയിരം", "ହଜାର", "ਹਜ਼ਾਰ", "ਹਜਾਰ"],
    100_000: ["lakh", "lakhs", "lac", "lacs", "laakh", "लाख", "لاکھ", "લાખ", "লাখ", "লক্ষ", "லட்சம்", "లక్ష", "లక్షల",
              "ಲಕ್ಷ", "ലക്ഷം", "ଲକ୍ଷ", "ਲੱਖ"],
    10_000_000: ["crore", "crores", "cr", "karod", "करोड़", "कोटी", "کروڑ", "કરોડ", "কোটি", "கோடி", "కోటి", "ಕೋಟಿ",
                 "കോടി", "କୋଟି", "ਕਰੋੜ"],
}
FRACTIONS: dict[Fraction, list[str]] = {
    Fraction(3, 2): ["dedh", "derh", "डेढ़", "દોઢ", "ડોઢ", "ڈیڑھ", "ਡੇਢ"],
    Fraction(5, 2): ["dhai", "adhai", "ढाई", "अढ़ाई", "અઢી", "ڈھائی", "ਢਾਈ"],
    Fraction(1, 2): ["half", "aadha", "adha", "आधा", "અડધો", "અડધા", "અડધું", "آدھا"],
}
# sava X = X + ¼, saadhe X = X + ½, paune X = X − ¼
MODIFIERS: dict[Fraction, list[str]] = {
    Fraction(1, 4): ["sava", "savva", "सवा", "સવા", "سوا", "ਸਵਾ"],
    Fraction(1, 2): ["saadhe", "sadhe", "saade", "साढ़े", "સાડા", "ساڑھے", "ਸਾਢੇ"],
    Fraction(-1, 4): ["paune", "pone", "पौने", "પોણા", "پونے", "ਪੌਣੇ"],
}
CURRENCY = ["₹", "rs", "rs.", "inr", "rupees", "rupee", "rupaye", "rupaiye", "rupiya", "rupya", "रुपये", "रुपए", "रुपया",
            "रुपयांचे", "રૂપિયા", "રૂ", "টাকা", "টকা", "ரூபாய்", "రూపాయలు", "ರೂಪಾಯಿ", "രൂപ", "ଟଙ୍କା", "ਰੁਪਏ", "روپے", "روپیہ"]
CONNECTORS = ["and", "aur", "और", "ane", "અને", "ane", "ও", "আৰু", "ਅਤੇ", "اور"]
# Grammatical endings glued to Indic words ("હજારની", "લાખમાં", "लाखों").
SUFFIXES = ["ની", "નો", "નું", "ના", "માં", "થી", "ને", "નાં", "ों", "ची", "चा", "चे", "ला", "ত", "র", "ம்", "ల", "ക്ക്"]
# Romanised words that are also common Hindi/English words; accept only with a unit or in a number context.
AMBIGUOUS = {key(w) for w in ["do", "nau", "saath", "sath", "ek", "das", "teen", "char", "saat", "so", "sau"]}


@dataclass(frozen=True)
class NumberMatch:
    value: Fraction
    start: int  # token index, inclusive
    end: int  # token index, exclusive
    char_start: int
    char_end: int
    unit: int  # largest multiplier used (1 when none)
    words: bool  # number words were involved
    currency: bool
    ordinal: bool = False

    @property
    def is_integer(self) -> bool:
        return self.value.denominator == 1

    @property
    def confidence(self) -> float:
        if not self.words:
            return 0.98
        return 0.95 if (self.unit > 1 or self.currency) else 0.9

    @property
    def rupees(self) -> int:
        return int(self.value)


def _k(word: str) -> str:
    return key(normalise(word))


@cache
def lexicon(lang: str) -> dict[str, int]:
    lex: dict[str, int] = {}
    for i, w in enumerate(ENGLISH):
        lex[_k(w)] = i
    for w, v in ENGLISH_TENS.items():
        lex[_k(w)] = v
    if lang in {"hi", "ur", "en", "pa"}:
        for i, w in enumerate(HINDI_ROMAN):
            if lang != "en" or _k(w) not in AMBIGUOUS:
                lex[_k(w)] = i
    if lang in {"hi", "ur"}:
        for i, w in enumerate(HINDI_DEVANAGARI):
            lex[_k(w)] = i
        for w, v in HINDI_VARIANTS.items():
            lex.setdefault(_k(w), v)
    if lang == "gu":
        for i, w in enumerate(GUJARATI):
            lex[_k(w)] = i
        for w, v in GUJARATI_VARIANTS.items():
            lex.setdefault(_k(w), v)
    if lang in SMALL:
        words = SMALL[lang].split()
        for i, w in enumerate(words[:11]):
            lex[_k(w)] = i
        for i, w in enumerate(words[11:]):
            lex[_k(w)] = (i + 2) * 10
    return lex


@cache
def _table(kind: str) -> dict[str, Fraction | int]:
    source: dict[object, list[str]] = {"unit": UNITS, "fraction": FRACTIONS, "modifier": MODIFIERS}[kind]  # type: ignore[assignment]
    return {_k(w): v for v, words in source.items() for w in words}  # type: ignore[misc]


_CURRENCY = {_k(w) for w in CURRENCY}
_CONNECTORS = {_k(w) for w in CONNECTORS}


def _lookup(table: dict[str, object], token: str, prefix: bool = False) -> object | None:
    k = key(token)
    if k in table:
        return table[k]
    if is_latin(token):
        return None
    for suffix in SUFFIXES:
        if token.endswith(suffix) and token[: -len(suffix)] in table:
            return table[token[: -len(suffix)]]
    if prefix:
        for word, value in table.items():
            if not is_latin(word) and len(word) >= 2 and token.startswith(word) and len(token) - len(word) <= 4:
                return value
    return None


def classify(token: str, lang: str) -> tuple[str, object] | None:
    import re

    if m := re.fullmatch(r"(\d+(?:\.\d+)?)(k)?", token):
        value = Fraction(m.group(1))
        return ("value", value * 1000) if m.group(2) else ("digits", value)
    if m := re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th|vi|vin|वीं|वी|મું|મા|મી)", token):
        return "ordinal", Fraction(int(m.group(1)))
    if key(token) in _CURRENCY or token.startswith("₹"):
        return "currency", None
    if key(token) in _CONNECTORS:
        return "connector", None
    if (v := _lookup(_table("modifier"), token)) is not None:  # type: ignore[arg-type]
        return "modifier", v
    if (v := _lookup(_table("fraction"), token)) is not None:  # type: ignore[arg-type]
        return "fraction", v
    if (v := _lookup(_table("unit"), token, prefix=True)) is not None:  # type: ignore[arg-type]
        return "unit", v
    lex = lexicon(lang)
    if is_latin(token) and "-" in token:
        parts = token.split("-")
        if len(parts) == 2 and _k(parts[0]) in lex and _k(parts[1]) in lex:
            tens, ones = lex[_k(parts[0])], lex[_k(parts[1])]
            if tens % 10 == 0 and tens >= 20 and ones < 10:
                return "word", Fraction(tens + ones)
    if (v := _lookup(lex, token)) is not None:  # type: ignore[arg-type]
        return "word", Fraction(int(v))  # type: ignore[call-overload]
    return None


def _parse_at(tokens: list[Token], i: int, lang: str) -> NumberMatch | None:
    kinds = [classify(t.text, lang) for t in tokens]
    currency = False
    j = i
    if kinds[j] and kinds[j][0] == "currency":  # type: ignore[index]
        currency = True
        j += 1
    begin = j
    total = Fraction(0)
    group: Fraction | None = None
    modifier: Fraction | None = None
    hundreds = False
    last_unit = 10**12
    largest = 1
    words = False
    ordinal = False
    last_word_value: int | None = None
    while j < len(tokens):
        kind = kinds[j]
        if kind is None:
            break
        name, value = kind
        if name == "modifier":
            if modifier is not None or group is not None:
                break
            modifier = value  # type: ignore[assignment]
            words = True
        elif name == "fraction":
            if group is not None:
                break
            group = value  # type: ignore[assignment]
            words = True
        elif name in {"digits", "word", "value", "ordinal"}:
            v: Fraction = value  # type: ignore[assignment]
            if group is not None:
                # "twenty five", "paanch sau pachaas"
                tens_join = name == "word" and last_word_value is not None and last_word_value % 10 == 0 \
                    and 20 <= last_word_value <= 90 and v < 10 and not hundreds
                if tens_join or (hundreds and v < 100):
                    group += v
                    hundreds = False
                    last_word_value = None
                    j += 1
                    continue
                break
            group = v
            if name == "value":
                largest = max(largest, 1000)
            if modifier is not None:
                group += modifier
                modifier = None
            words = words or name == "word"
            ordinal = name == "ordinal"
            last_word_value = int(v) if name == "word" and v.denominator == 1 else None
        elif name == "unit":
            m: int = value  # type: ignore[assignment]
            if group is None:
                if modifier is None:
                    break
                group, modifier = 1 + modifier, None
            if m == 100:
                if hundreds:
                    break
                group *= 100
                hundreds = True
            else:
                if m >= last_unit:
                    break
                total += group * m
                group, hundreds, last_unit = None, False, m
            largest = max(largest, m)
            last_word_value = None
        elif name == "connector":
            nxt = kinds[j + 1] if j + 1 < len(kinds) else None
            if group is not None or total == 0 or not nxt or nxt[0] not in {"digits", "word", "fraction", "modifier"}:
                break
        elif name == "currency":
            if total == 0 and group is None:
                break
            currency = True
            j += 1
            break
        j += 1
    if total == 0 and group is None:
        return None
    value = total + (group or 0)
    end = j
    if end < len(tokens) and kinds[end] and kinds[end][0] == "currency":  # type: ignore[index]
        currency, end = True, end + 1
    # A trailing connector is not part of the number.
    while end > begin and kinds[end - 1] and kinds[end - 1][0] == "connector":  # type: ignore[index]
        end -= 1
    start_tok = i if currency and i < begin else begin
    return NumberMatch(value, start_tok, end, tokens[start_tok].start, tokens[end - 1].end, largest, words, currency, ordinal)


def find_numbers(text: str, lang: str = "en") -> list[NumberMatch]:
    _, tokens = tokenize(text)
    out: list[NumberMatch] = []
    i = 0
    while i < len(tokens):
        match = _parse_at(tokens, i, lang)
        if match is None or match.end <= i:
            i += 1
            continue
        single_ambiguous = (match.words and match.unit == 1 and not match.currency and match.end - match.start == 1
                            and is_latin(tokens[match.start].text) and key(tokens[match.start].text) in AMBIGUOUS)
        if not single_ambiguous:
            out.append(match)
        i = match.end
    return out


def parse_amount_rupees(text: str, lang: str = "en") -> int | None:
    """The single amount in `text`, in whole rupees; None when there is none or it is not whole."""
    amounts = [m for m in find_numbers(text, lang) if not m.ordinal]
    if not amounts:
        return None
    best = max(amounts, key=lambda m: (m.unit > 1 or m.currency, m.value))
    return int(best.value) if best.value.denominator == 1 else int(best.value.__round__())

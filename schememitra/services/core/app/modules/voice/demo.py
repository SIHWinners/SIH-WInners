"""Demo utterances for the voice flow (fictional personas, spec §14).

In BHASHINI_MODE=sandbox there is no speech recognition service, so the SANDBOX ASR
returns the next scripted utterance for the session language and the UI labels the
transcript SANDBOX. The same lines appear as tappable demo chips. Everything after the
transcript — number parsing, slot extraction, clarification, read-back — is real."""

SCRIPTS: dict[str, list[str]] = {
    # Persona 1 — Savitaben Rathwa, Dahod (Gujarati)
    "gu": [
        "મારું નામ સવિતાબેન રાઠવા છે, મારી ઉંમર ચોત્રીસ વર્ષ છે, હું દાહોદ જિલ્લામાં રહું છું.",
        "હું સ્ત્રી છું, અનુસૂચિત જાતિમાંથી છું, કોઈ વિકલાંગતા નથી.",
        "મારે બે દુધાળા પશુ લેવા છે, કુલ ખર્ચ સાઠ હજાર રૂપિયા, અને લોન પણ સાઠ હજાર જોઈએ.",
        "ઘરની વર્ષની આવક એક લાખ વીસ હજાર છે, હું ચાર ધોરણ સુધી ભણી છું.",
        "હું સખી મંડળની સભ્ય છું, અને મારી પાસે બીજી કોઈ લોન નથી.",
        "હા, બરાબર છે.",
    ],
    # Persona 2 — Ramesh Meghwal, Barmer (Hindi)
    "hi": [
        "मेरा नाम रमेश कानाराम मेघवाल है, उम्र इकतालीस साल, बाड़मेर ज़िले में रहता हूँ।",
        "मैं पुरुष हूँ, अनुसूचित जाति से हूँ, कोई विकलांगता नहीं है।",
        "सिलाई का काम बढ़ाना है, पूरा खर्च साढ़े चार लाख, और लोन चार लाख चाहिए।",
        "घर की सालाना कमाई एक लाख अस्सी हज़ार है, दसवीं तक पढ़ा हूँ।",
        "स्वयं सहायता समूह का सदस्य नहीं हूँ, और कोई लोन नहीं चल रहा।",
        "हाँ, सही है।",
    ],
    "en": [
        "My name is Savitaben Rathwa, I am 34 years old and I live in Dahod district.",
        "I am a woman, from a Scheduled Caste, and I have no disability.",
        "I want to buy two milch animals, the total cost is sixty thousand rupees and I need a loan of sixty thousand.",
        "Our family income is 1.2 lakh a year and I studied up to class 4.",
        "I am a member of a self help group and I have no other loan running.",
        "Yes, that is correct.",
    ],
}

READBACK_CONFIRM = {"gu": "હા, બરાબર છે.", "hi": "हाँ, सही है।", "en": "Yes, that is correct."}


def scripted(lang: str, index: int) -> str | None:
    lines = SCRIPTS.get(lang)
    if not lines:
        return None
    return lines[min(index, len(lines) - 1)]

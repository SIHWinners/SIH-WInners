"""Phase 4 gate (API level): number words, slot extraction in Gujarati/Hindi/English, the
conversation state machine, clarification, correction, LLM guard rails, fallbacks and the
voice read-back used as consent evidence."""

import json

import pytest

from app.config import get_settings
from app.core.resilience import registry, set_chaos
from app.modules.eligibility.loader import invalidate_ruleset
from app.modules.voice import llm, speech
from app.modules.voice.conversation import ConversationState, step
from app.modules.voice.demo import READBACK_CONFIRM, SCRIPTS
from app.modules.voice.numbers import GUJARATI, HINDI_DEVANAGARI, HINDI_ROMAN, SMALL, find_numbers, lexicon, parse_amount_rupees
from app.modules.voice.slots import extract, yes_no
from app.seed.partners import seed_partners
from app.seed.personas import PERSONAS
from app.seed.schemes import seed_schemes
from tests.conftest import login


@pytest.fixture(scope="module", autouse=True)
async def _seeded():  # type: ignore[no-untyped-def]
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        await seed_schemes(session)
        await seed_partners(session)
        await session.commit()
    invalidate_ruleset()
    yield


AMOUNTS = [
    ("dedh lakh", "hi", 150_000), ("2.5 lakh", "en", 250_000), ("pachas hazaar", "hi", 50_000),
    ("pachaas hajar", "hi", 50_000), ("एक लाख बीस हज़ार", "hi", 120_000), ("₹1,20,000", "en", 120_000),
    ("sixty thousand rupees", "en", 60_000), ("સાઠ હજાર રૂપિયા", "gu", 60_000), ("એક લાખ વીસ હજાર", "gu", 120_000),
    ("દોઢ લાખ", "gu", 150_000), ("અઢી લાખ", "gu", 250_000), ("साढ़े चार लाख", "hi", 450_000),
    ("sava do lakh", "hi", 225_000), ("paune do lakh", "hi", 175_000), ("paanch sau pachaas", "hi", 550),
    ("one lakh twenty thousand", "en", 120_000), ("twenty-five thousand", "en", 25_000), ("60k", "en", 60_000),
    ("rs.5000", "en", 5_000), ("ਡੇਢ ਲੱਖ", "pa", 150_000), ("৩ লাখ", "bn", 300_000), ("ஐம்பது ஆயிரம்", "ta", 50_000),
    ("ఇరవై వేల రూపాయలు", "te", 20_000), ("૧,૨૦,૦૦૦", "gu", 120_000), ("दो करोड़", "hi", 20_000_000),
    ("ढाई लाख", "hi", 250_000), ("पाँच लाख एक", "hi", 500_001), ("ایک لاکھ", "ur", 100_000), ("दहा हजार", "mr", 10_000),
]


@pytest.mark.parametrize(("text", "lang", "rupees"), AMOUNTS)
def test_indian_amounts(text: str, lang: str, rupees: int) -> None:
    assert parse_amount_rupees(text, lang) == rupees


def test_number_tables_are_complete_and_consistent() -> None:
    assert len(HINDI_DEVANAGARI) == len(HINDI_ROMAN) == len(GUJARATI) == 100
    assert all(len(words.split()) == 19 for words in SMALL.values())
    for lang in ("hi", "gu", "en", "ur", "ta"):
        assert lexicon(lang)  # builds without key collisions raising
    assert lexicon("gu")["ચોત્રીસ"] == 34 and lexicon("hi")["सैंतीस"] == 37


def test_ambiguous_romanised_words_need_context() -> None:
    assert find_numbers("main uske saath gaya", "hi") == []  # "saath" = with
    assert parse_amount_rupees("saath hazaar", "hi") == 60_000
    assert find_numbers("de do", "hi") == []


def test_yes_no_across_languages() -> None:
    for text in ("haan ji", "हाँ, सही है", "હા, બરાબર છે", "ஆம்", "ہاں", "yes that is right"):
        assert yes_no(text) is True, text
    for text in ("nahi", "नहीं", "ના", "இல்லை", "no"):
        assert yes_no(text) is False, text


def _persona_values(persona: str) -> dict[str, object]:
    p = PERSONAS[persona]
    keep = ["age", "gender", "social_category", "has_disability", "district_code", "state_code", "annual_family_income_paise",
            "education_level", "business_type", "project_cost_paise", "loan_needed_paise", "shg_member", "existing_loans"]
    return {k: p.facts[k] for k in keep}


@pytest.mark.parametrize(("lang", "persona"), [("gu", "savitaben"), ("hi", "ramesh"), ("en", "savitaben")])
def test_scripted_conversation_fills_the_form(lang: str, persona: str) -> None:
    conv = ConversationState(lang)
    for line in SCRIPTS[lang][:-1]:
        reply = step(conv, line)
        assert not reply.not_understood, (line, reply.text)
    assert conv.state == "confirm"
    assert step(conv, SCRIPTS[lang][-1]).text
    assert conv.state == "done" and conv.handoff == "rules" and conv.user_turns == 6
    values = conv.values
    expected = _persona_values(persona)
    assert {k: values.get(k) for k in expected} == expected
    assert values["disability_pct"] == 0 and values["full_name"]


def test_low_confidence_value_is_read_back_before_use() -> None:
    conv = ConversationState("en")
    conv.asked = ["full_name", "age", "district_code"]
    reply = step(conv, "My name is Kavita Devi, I am 30 years old, I live in Dahood")
    assert conv.state == "clarify" and conv.clarify and conv.clarify["value"] == "GJ-DAH"
    assert "Dahod" in reply.text and "district" in reply.text
    step(conv, "haan")
    assert conv.values["district_code"] == "GJ-DAH" and conv.slots["district_code"]["method"] == "confirmed"
    assert conv.state == "intake" and conv.asked == ["gender", "social_category", "has_disability"]


def test_correction_at_confirm_step() -> None:
    conv = ConversationState("hi")
    for line in SCRIPTS["hi"][:-1]:
        step(conv, line)
    assert conv.state == "confirm"
    step(conv, "उम्र गलत है, उम्र बयालीस साल है")
    assert conv.values["age"] == 42 and conv.state == "confirm"
    reply = step(conv, "लोन गलत है")
    assert conv.state == "intake" and conv.asked == ["loan_needed_paise"] and "लोन" in reply.text
    step(conv, "साढ़े तीन लाख")
    assert conv.values["loan_needed_paise"] == 350_000_00 and conv.state == "confirm"


def test_monthly_income_is_annualised_with_confirmation() -> None:
    slots = extract("meri kamai 10 hazaar mahina hai", "hi")
    assert slots["annual_family_income_paise"].value == 120_000_00
    assert slots["annual_family_income_paise"].confidence < 0.85


def test_caste_and_gender_are_never_guessed_from_names() -> None:
    slots = extract("mera naam Savitaben Rathwa hai", "hi")
    assert "gender" not in slots and "social_category" not in slots


def test_llm_redaction_and_parsing() -> None:
    redacted = llm.redact("Savitaben Rathwa, phone 98765 43210, aadhaar 1234-5678-9012", "Savitaben Rathwa")
    assert "Savitaben" not in redacted and "98765" not in redacted and "9012" not in redacted
    parsed = llm._parse(json.dumps({"business_type": {"value": "dairy", "confidence": 0.99},
                                    "loan_needed_rupees": {"value": 60000, "confidence": 0.9},
                                    "social_category": {"value": "brahmin", "confidence": 0.9}}), "x")
    assert parsed["business_type"].confidence == llm.MAX_LLM_CONFIDENCE
    assert parsed["loan_needed_paise"].value == 60_000_00 and "social_category" not in parsed


async def test_llm_slots_only_fill_gaps_and_fail_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_mode", "ollama")
    prompts: list[str] = []

    async def fake_call(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps({"business_type": {"value": "handicraft", "confidence": 0.8}, "age": {"value": 99, "confidence": 0.9}})

    monkeypatch.setattr(llm, "_call", fake_call)
    slots = await llm.extract("Asha Devi, 9876543210, I make baskets", "en", "Asha Devi", ["business_type"])
    assert set(slots) == {"business_type"} and slots["business_type"].method == "llm"
    assert "9876543210" not in prompts[0] and "Asha" not in prompts[0]

    async def broken(prompt: str) -> str:
        raise ConnectionError("ollama down")

    monkeypatch.setattr(llm, "_call", broken)
    assert await llm.extract("I make baskets", "en", None, ["business_type"]) == {}
    assert registry.last_path["llm"] == "fallback"


def test_glossary_terms_survive_translation() -> None:
    text = "आपकी EMI (मासिक किस्त) 8,440 रुपये है"
    protected, terms = speech.protect(text, "hi")
    assert "EMI (मासिक किस्त)" not in protected and terms == ["emi"]
    assert speech.restore(protected.replace("आपकी", "Your"), terms, "gu").startswith("Your EMI (માસિક હપ્તો)")


async def test_voice_session_api_gujarati(client) -> None:  # type: ignore[no-untyped-def]
    start = await client.post("/v1/voice/sessions", json={"lang": "gu"})
    assert start.status_code == 200, start.text
    body = start.json()
    sid = body["session_id"]
    assert body["state"] == "intake" and body["reply_text"].startswith("નમસ્તે") and body["tts"] == "device"
    assert body["demo_utterances"] == SCRIPTS["gu"] and body["asked"] == ["full_name", "age", "district_code"]

    # First turn by (fake) audio: SANDBOX ASR returns the scripted line, labelled.
    audio = await client.post(f"/v1/voice/sessions/{sid}/utterance", files={"audio": ("a.webm", b"\x1aE\xdf\xa3fake-opus", "audio/webm")})
    assert audio.status_code == 200, audio.text
    turn = audio.json()
    assert turn["transcript_engine"] == "sandbox" and turn["sandbox"] and turn["transcript"] == SCRIPTS["gu"][0]
    assert turn["slots"]["district_code"]["value"] == "GJ-DAH" and turn["filled"] == 3

    for line in SCRIPTS["gu"][1:]:
        res = await client.post(f"/v1/voice/sessions/{sid}/utterance", data={"text": line})
        assert res.status_code == 200, res.text
        turn = res.json()
    assert turn["state"] == "done" and turn["handoff"] == "rules" and turn["turn"] == 6
    assert turn["filled"] == turn["total"] >= 13
    assert turn["slots"]["loan_needed_paise"]["value"] == 60_000_00

    again = await client.get(f"/v1/voice/sessions/{sid}")
    assert again.json()["state"] == "done"


async def test_asr_outage_falls_back_to_typing(client) -> None:  # type: ignore[no-untyped-def]
    sid = (await client.post("/v1/voice/sessions", json={"lang": "hi"})).json()["session_id"]
    set_chaos("bhashini_asr", True)
    try:
        res = await client.post(f"/v1/voice/sessions/{sid}/utterance", files={"audio": ("a.webm", b"fake", "audio/webm")})
        if speech.whisper_available():
            assert res.status_code in (200, 503)
        else:
            assert res.status_code == 503 and res.json()["user_message_key"] == "voice.asr_unavailable"
        typed = await client.post(f"/v1/voice/sessions/{sid}/utterance", data={"text": SCRIPTS["hi"][0]})
        assert typed.status_code == 200 and typed.json()["transcript_engine"] == "typed"
    finally:
        set_chaos("bhashini_asr", False)

    bad = await client.post(f"/v1/voice/sessions/{sid}/utterance", files={"audio": ("a.exe", b"MZ", "application/x-msdownload")})
    assert bad.status_code == 415


async def test_voice_session_is_private_once_owned(client) -> None:  # type: ignore[no-untyped-def]
    owner = await login(client, PERSONAS["kavya"].phone)
    sid = (await client.post("/v1/voice/sessions", json={"lang": "ta"}, headers=owner)).json()["session_id"]
    assert (await client.get(f"/v1/voice/sessions/{sid}")).status_code == 404
    assert (await client.get(f"/v1/voice/sessions/{sid}", headers=owner)).status_code == 200


async def test_readback_and_voice_confirmation_become_consent_evidence(client) -> None:  # type: ignore[no-untyped-def]
    savita = PERSONAS["savitaben"]
    headers = await login(client, savita.phone)
    lat, lng = savita.location
    nearby = (await client.get("/v1/partners/nearby", params={"lat": lat, "lng": lng, "scheme": savita.expected_scheme,
                                                               "category": "sc"})).json()
    draft = {"client_uuid": "test-savita-voice-1", "lang": "gu",
             "personal": {"full_name": "સવિતાબેન રાઠવા", "phone": savita.phone},
             "facts": {**savita.facts, "lat": lat, "lng": lng}, "scheme_code": savita.expected_scheme,
             "plan": {"principal_paise": 60_000_00, "rate_bps": 500, "tenure_months": 36, "moratorium_months": 3},
             "partner_id": nearby["partners"][0]["id"]}
    app = await client.post("/v1/applications", json=draft, headers=headers)
    assert app.status_code == 200, app.text
    app_id = app.json()["id"]

    assert (await client.post("/v1/voice/readback", json={"application_id": app_id})).status_code == 401
    rb = await client.post("/v1/voice/readback", json={"application_id": app_id}, headers=headers)
    assert rb.status_code == 200, rb.text
    readback = rb.json()
    assert "સવિતાબેન રાઠવા" in readback["text"] and "60" in readback["text"] and readback["demo_reply"] == READBACK_CONFIRM["gu"]

    unclear = (await client.post(f"/v1/voice/readback/{app_id}/reply", data={"text": "hmm"}, headers=headers)).json()
    assert unclear["intent"] == "unclear"
    correct = (await client.post(f"/v1/voice/readback/{app_id}/reply", data={"text": "લોન ખોટી છે"}, headers=headers)).json()
    assert correct["intent"] == "correct" and correct["field"] == "loan_needed_paise"
    ok = (await client.post(f"/v1/voice/readback/{app_id}/reply", files={"audio": ("a.webm", b"fake", "audio/webm")},
                            headers=headers)).json()
    assert ok["intent"] == "confirm" and ok["sandbox"] and ok["evidence"]["voice_confirmation"] == READBACK_CONFIRM["gu"]

    consent = await client.post(f"/v1/applications/{app_id}/consent", headers=headers,
                                json={"method": "voice", "language": "gu", "evidence": ok["evidence"]})
    assert consent.status_code == 200, consent.text
    other = await login(client, PERSONAS["ramesh"].phone)
    assert (await client.post("/v1/voice/readback", json={"application_id": app_id}, headers=other)).status_code == 404

# Architecture decision records

Short ADRs. Newest at the bottom. "Known limitations" are collected at the end.

## ADR-001 — Two runtime profiles: `local` (no Docker) and `compose` (production-shaped)
**Context.** The build machine has no Docker, Postgres or Redis. Judges' laptops may not either.
**Decision.** The core service talks to storage only through adapters:
| Concern | `compose` profile | `local` profile (default dev/demo/test) |
|---|---|---|
| Database | PostgreSQL 16 + PostGIS 3 (asyncpg, GeoAlchemy2, RLS) | SQLite (aiosqlite), app-level authz, haversine search |
| Cache / rate limit | Redis 7 | in-process TTL cache |
| Job queue | ARQ on Redis | in-process asyncio task runner |
| Object storage | MinIO / Supabase Storage (S3 API, SSE) | local folder, AES-256-GCM encrypted blobs |
Selection is by `DATABASE_URL`, `REDIS_URL`, `STORAGE_MODE`. The same models, services and tests run on both.
**Consequence.** Zero-internet demo mode runs on any laptop with Python + Node. PostGIS-specific paths (KNN `<->`, RLS policies) are exercised only under compose.

## ADR-002 — PDF generation with fpdf2 + HarfBuzz instead of WeasyPrint
WeasyPrint needs GTK/Pango native libraries that are painful on Windows. fpdf2 with `uharfbuzz` text shaping renders Devanagari/Gujarati/Tamil conjuncts and matras correctly, embeds subsetted Noto fonts, and is pure wheels. Output stays well under 400 KB.

## ADR-003 — SHAP values from XGBoost's native TreeSHAP
`Booster.predict(pred_contribs=True)` returns exact TreeSHAP contributions. This removes the `shap` → `numba` dependency chain (slow install, frequent Python-version lag) with identical numbers.

## ADR-004 — PyJWT (+cryptography) instead of python-jose
python-jose has weak Ed25519/EdDSA support and slow maintenance. PyJWT supports `EdDSA` and `HS256` and is widely audited. Used for QR JWS (Ed25519) and session JWTs (HS256, Supabase-compatible claims).

## ADR-005 — In-house JSON-Logic evaluator (Python + TypeScript twins)
Eligibility must be deterministic and auditable offline. `json-logic-py` is unmaintained. We implement a small, whitelisted operator subset (`var`, comparisons, `and/or/!`, `in`, `missing`, `if`, arithmetic) in both languages, driven by one shared fixture file so the twins cannot drift. The evaluator records a trace for each top-level condition.

## ADR-006 — Task runner: `Makefile` delegating to `scripts/make.mjs`
`make` is not installed on Windows by default. The Makefile targets call `node scripts/make.mjs <target>`, so `make dev` (Linux/macOS/CI) and `pnpm run dev` / `node scripts/make.mjs dev` (Windows) behave identically.

## ADR-007 — Auth: Supabase-compatible JWTs with a dev OTP issuer
`AUTH_MODE=dev` — the core issues HS256 JWTs with Supabase claim shape (`sub`, `role=authenticated`, `app_metadata.app_role`, `phone`) after a console-printed OTP. `AUTH_MODE=supabase` — tokens come from Supabase Auth and are verified with `SUPABASE_JWT_SECRET`. Gateway and core both verify (defence in depth). On Postgres, the core sets `request.jwt.claims` per transaction so RLS policies apply.

## ADR-008 — LLM defaults
Ollama is available locally with `llama3.2:3b`; the spec prefers Llama 3.1 8B. `LLM_MODEL` is configurable; `make models` pulls `llama3.1:8b` when resources allow. The deterministic number/slot parser always runs first and wins on conflicts. Tests run with `LLM_MODE=off`. External LLM endpoints (`LLM_MODE=openai_compat`) receive PII-redacted text only and are off by default.

## ADR-009 — OCR engine: RapidOCR (PP-OCR ONNX) instead of full PaddlePaddle
PaddlePaddle wheels are ~500 MB and fragile on Windows. RapidOCR runs the same PP-OCR detection/recognition models via ONNX Runtime (tens of MB). `OCR_MODE=rapidocr|sandbox`. Sandbox OCR recognises seeded demo documents by SHA-256 and otherwise reports low confidence, which routes the user to DigiLocker or manual entry — the documented fallback.

## ADR-010 — Contracts: openapi-typescript + openapi-fetch
FastAPI's OpenAPI is exported to `packages/contracts/openapi.json`; `openapi-typescript` generates `src/generated/api.ts`. Web, gateway and mobile use `openapi-fetch` typed clients, so there are no hand-written duplicate API types. Zod is used only at the gateway edge for webhook payloads that do not go through the core schema.

## ADR-011 — Text-safe "ink" variants for status and accent colours
The spec's warning (#B7791F, 3.6:1 on white) and accent (#E07A1F, 3.0:1) fail WCAG AA for body text. We keep them for fills, borders, icons and progress bars (non-text, 3:1 required) and add `warningInk` #8A5A12, `accentInk` #9A4A0A, `successInk`, `dangerInk` for text. `borderStrong` moved from #98A2B3 to #7A8699 to reach 3:1 for input borders. `packages/ui/scripts/check-contrast.mjs` enforces every declared pair in light and dark and fails CI on drift between tokens.ts and tokens.css.

## ADR-012 — Localisation scope: citizens in 13 languages, officers in English + Hindi
Every citizen-facing string (intake, rules, money, partners, documents, tracking, SMS, voice prompts, errors, consent) ships in all 13 languages. Partner-officer, admin and policy consoles are used by bank/agency staff and ship in English and Hindi (`officer` namespace). The CI key checker enforces both rules, placeholder parity and stale keys. All non-English catalogues are machine drafts marked `review_status: machine_draft` for native-speaker review during the pilot.

## ADR-013 — Amounts spoken as numerals + localised unit words
"₹1,25,000" is read as "1 lakh 25 thousand rupees" with *lakh/thousand/rupees* in the user's language. Full number-to-words for 13 languages (irregular 1–99 words in most Indic languages) adds risk for no comprehension gain: every TTS voice reads numerals natively in-language, and unit words are how amounts are actually spoken.

## ADR-014 — Rate slider covers the deck range and every scheme's official rate
The deck shows EMIs for 6.5%–15%. Several verified concessional rates are lower (NBCFDC micro finance 5%). The calculator slider defaults to 6.5%–15% in 0.25% steps and extends its lower bound to the selected scheme's rate when that rate is lower, so an official rate is never clamped into a wrong number.

## ADR-015 — Persona categories are assigned, not inferred from surnames
Demo personas are fictional. Their social category is chosen to exercise a specific scheme (e.g. Savitaben → NSFDC micro credit) and is never derived from a name. The product itself never infers caste or community from a name.

## ADR-016 — Scheme parameter provenance
NBCFDC individual and education loan parameters were checked against nbcfdc.gov.in on 2026-09-16 (`needs_verification: false`). All other values come from Ministry/corporation summaries or the pitch deck and carry `needs_verification: true`, shown as an "illustrative" badge in admin. MUDRA Kishor is included as a non-MoSJE, open-to-all fallback so near-miss applicants get a next-best option.

## ADR-017 — Portable PostgreSQL + PostGIS for verifying the compose profile without Docker
EDB PostgreSQL 16 binaries plus the OSGeo PostGIS 3.6 bundle run from a folder. `TEST_DATABASE_URL=postgresql+asyncpg://…` makes the pytest suite apply the real Alembic migrations (PostGIS geometry, GiST/BRIN/trigram indexes, partitions, RLS, append-only trigger) instead of `create_all`, so the Postgres-only code paths are exercised. The migration splits SQL scripts per statement because asyncpg rejects multi-statement strings.

## ADR-018 — Voice intake: deterministic parsing on source-language text, localized reply templates
Spec §9.1 describes ASR → NMT to an English pivot → slot extraction → English reply → NMT back → TTS. We run slot extraction directly on the source-language transcript with per-language lexicons (13 languages) and an Indian number-word parser, and speak replies from the pre-translated i18n catalogue. This removes two machine-translation hops from every turn (latency, cost, garbling) and keeps the flow fully offline. NMT stays behind the adapter (Bhashini → glossary-protected fallback) and is only needed to pivot text for an LLM. Number-word coverage is honest and bounded: digits in every Indian script and unit/fraction words (hazaar, lakh, crore, dedh, dhai, sava, saadhe, paune) in all 13 languages; full 0–99 word tables for Hindi (Devanagari + romanised) and Gujarati; 0–10 plus tens elsewhere. Romanised words that are also ordinary words ("saath", "do") count as numbers only with a unit or when a number was asked for.

## ADR-019 — LLM values are always confirmed, never auto-accepted
When LLM_MODE is on, the model only fills slots the rules left empty, its confidence is capped at 0.7 (below the 0.75 auto-accept threshold), so every LLM value is read back for a yes/no. Name, phone and Aadhaar-like digit runs are redacted from prompts and `full_name` is never taken from the model. Enum values outside the schema are dropped. Failure or timeout falls back to rules + form (§13).

## ADR-020 — SANDBOX speech recognition returns the scripted demo line
Without Bhashini keys or a local faster-whisper model there is nothing that can honestly transcribe audio. In BHASHINI_MODE=sandbox the ASR adapter therefore returns the next scripted utterance for the session language (Gujarati, Hindi, English persona scripts), and the UI labels the transcript SANDBOX next to the text. Everything after the transcript (number parsing, slots, clarification, read-back, consent evidence) is the real code path. The admin chaos toggle `bhashini_asr` shows the fallback: faster-whisper if installed, otherwise the typed input. Audio is never stored; transcripts and slots are stored encrypted and anonymous sessions are purged after 24 h.

# SchemeMitra — build progress

**Current phase:** 5 — Partner portal & ML ranking
**Next task:** 5.1
**Resume:** read this file, `docs/DECISIONS.md`, then continue from the first unticked item.

```bash
pnpm install            # JS workspaces
cd services/core && uv sync --extra dev   # Python core
node scripts/make.mjs dev    # or `make dev` where make exists
```

## Master checklist

### Phase 1 — Foundation
- [x] 1.1 Monorepo: pnpm workspaces, Turborepo, shared tsconfig/eslint/prettier, .editorconfig, .gitignore
- [x] 1.2 Cross-platform task runner (`Makefile` + `scripts/make.mjs`): dev, seed, test, demo, reset, models
- [x] 1.3 `.env.example` with every env var + adapter modes
- [x] 1.4 Core service skeleton: FastAPI app factory, settings, structured PII-scrubbed logging, problem+json errors
- [x] 1.5 DB layer: SQLAlchemy 2 async models for every table in spec §8 (SQLite + Postgres/PostGIS)
- [x] 1.6 Alembic migrations incl. PostGIS geom, GiST/BRIN/trigram indexes, RLS policies (Postgres only)
- [x] 1.7 Crypto: AES-256-GCM envelope field encryption, UUIDv7, phone hashing
- [x] 1.8 Hash-chained append-only audit log + verify command
- [x] 1.9 Auth: phone OTP (console OTP in dev), Supabase-compatible JWT, roles, lockout
- [x] 1.10 Cache + job queue adapters (Redis/ARQ ↔ in-memory), storage adapter (local encrypted ↔ S3/MinIO)
- [x] 1.11 Gateway (Fastify): JWT verify, rate limit, proxy /v1 → core, WebSocket push, internal event hook
- [x] 1.12 Design tokens package (CSS vars, Tailwind v4 theme, RN theme) + contrast check script
- [x] 1.13 i18n package: 13 locales, glossary, missing-key checker, pseudo-locale
- [x] 1.14 Web app skeleton (Next.js 15, Tailwind v4) + OTP login for every role
- [x] 1.15 Docker Compose (Postgres+PostGIS, Redis, MinIO, core, worker, gateway, web, ollama profile) + Dockerfiles
- [x] 1.16 Seed script skeleton + demo users per role
- [x] 1.17 GitHub Actions CI (lint, types, tests, i18n, contrast, budgets, security scans)
- [x] 1.18 Phase 1 gate: tests green, stack boots, login works per role

### Phase 2 — Deterministic core
- [x] 2.1 Rule JSON Schema + JSON-Logic evaluator (Python) with trace
- [x] 2.2 Seed 12 scheme YAML files with source_url / verified_on / needs_verification
- [x] 2.3 Eligibility service: traces, localized sentences, near-miss + next-best scheme
- [x] 2.4 Rule engine tests: 100% coverage + hypothesis boundary tests
- [x] 2.5 Finance lib (Python, exact rationals): moratorium treatments, EMI, schedule, split, affordability, compare
- [x] 2.6 Finance lib (TS) + rules evaluator (TS) + offline bundle evaluator in packages/contracts
- [x] 2.7 Golden cross-language test (1,000 random cases, paise-exact)
- [x] 2.8 Partners: 150 seeded partners + monthly metrics in 5 states
- [x] 2.9 Health score, hard exclusions, distance decay, KNN (PostGIS) / haversine (SQLite), cache
- [x] 2.10 API: /v1/eligibility/evaluate, /v1/finance/emi, /v1/partners/nearby, /v1/rules/bundle (ETag)
- [x] 2.11 OpenAPI export → generated TS types in packages/contracts
- [x] 2.12 Web UI: rule trace view, calculator + schedule chart + split, partner list + lazy Leaflet map
- [x] 2.13 Phase 2 gate: personas 2 and 5 correct (API tests)

### Phase 3 — Citizen journey (PWA)
- [x] 3.1 5-step stepper + "What happens next" card + Zustand store + IndexedDB draft
- [x] 3.2 Form-first intake, one question per screen, listen buttons, Indian number format + words
- [x] 3.3 Document upload: blur/glare check, EXIF strip, re-encode, Aadhaar Verhoeff + masking
- [x] 3.4 OCR adapter (RapidOCR PP-OCR ↔ sandbox) + per-doc field templates
- [x] 3.5 Name normaliser + fuzzy matcher with anchors and reasons
- [x] 3.6 Readiness checker (presence, legibility, expiry, name/DOB/amount consistency)
- [x] 3.7 Applications API: create, readiness, submit; tracking ID with check char
- [x] 3.8 Ed25519 JWS QR + loan-file PDF (bilingual, Noto fonts, < 400 KB)
- [x] 3.9 Status machine + audit + notifications (ConsoleSms) + tracking timeline
- [x] 3.10 Consent notice + record (DPDP), withdraw + erase flow
- [x] 3.11 Phase 3 gate: persona 2 end to end on PWA (Playwright)

### Phase 4 — Voice & language
- [x] 4.1 Indian amount / number-word parser (13 languages incl. "dedh lakh", "pachas hazaar")
- [x] 4.2 Rule-based slot extractor + gazetteers; LLM slot extractor (Ollama / OpenAI-compatible, JSON schema)
- [x] 4.3 Conversation state machine intake → clarify → confirm → done
- [x] 4.4 ASR/NMT/TTS adapters: Bhashini (real), faster-whisper, sandbox; circuit breaker + timeouts
- [x] 4.5 Glossary-protected translation + TTS cache
- [x] 4.6 Voice UI: mic, live form-fill panel, typed fallback, demo utterance chips, timer
- [x] 4.7 Voice read-back + confirm/correct + consent evidence
- [x] 4.8 Phase 4 gate: persona 1 Gujarati voice flow ≤ 3 min (E2E)

### Phase 5 — Partner portal & ML ranking
- [ ] 5.1 Partner portal: queue table, QR scan (camera + paste), JWS verify
- [ ] 5.2 Split-view file review, name-match score, audit sidebar, keyboard shortcuts
- [ ] 5.3 Decisions: request docs / approve + sanction letter / reject with codes / disburse
- [ ] 5.4 WebSocket status push + SMS in citizen language (≤ 2 s)
- [ ] 5.5 Synthetic data generator (50k rows) + XGBoost LambdaMART training + NDCG@3
- [ ] 5.6 TreeSHAP reasons → plain-language templates; heuristic fallback
- [ ] 5.7 Model card with fairness parity check
- [ ] 5.8 Phase 5 gate: partner decision → citizen timeline + SMS

### Phase 6 — Offline, SMS, mobile, CSC
- [ ] 6.1 PWA service worker (Serwist), offline drafts, background sync, install prompt
- [ ] 6.2 Offline eligibility + EMI in browser marked provisional
- [ ] 6.3 SMS codec (pipe-delimited, checksum, ≤ 3 parts) TS + Python, inbound webhook reassembly
- [ ] 6.4 SMS STATUS lookup + IVR stub
- [ ] 6.5 DigiLocker adapter (sandbox + real OAuth2) + UI trigger on low OCR confidence
- [ ] 6.6 Expo app: citizen flow parity, SQLite store, sync queue, secure-store key, AES-GCM images + purge
- [ ] 6.7 CSC operator mode (web + mobile): queue, new applicant consent, bulk print, audit
- [ ] 6.8 Phase 6 gate: personas 3 and 4 pass

### Phase 7 — Policy dashboard & admin
- [ ] 7.1 Analytics events (anonymized buckets) + aggregate views + k-anonymity + Laplace noise
- [ ] 7.2 Dashboard: choropleth, uptake, funnel, rejection reasons, TAT, language mix, unmet demand, insight cards, CSV export
- [ ] 7.3 Admin: rule editor (validate, test persona, diff, publish version)
- [ ] 7.4 Admin: partner CRUD + metrics CSV upload
- [ ] 7.5 Admin: flags, adapter modes, SANDBOX badges, chaos toggles for every fallback
- [ ] 7.6 Admin: SMS phone mockup + simulator, demo controls (reset, simulate decision, fast-forward)
- [ ] 7.7 Synthetic 2,000 past applications
- [ ] 7.8 Phase 7 gate: C19 + every fallback demonstrable

### Phase 8 — Hardening & polish
- [ ] 8.1 Bundle budget check + Lighthouse run
- [ ] 8.2 axe accessibility pass on citizen + partner pages
- [ ] 8.3 Security: CSP/HSTS headers, upload hardening, dependency + secret scans
- [ ] 8.4 Load test (k6 script + runnable Python smoke) → PERFORMANCE.md
- [ ] 8.5 Dark mode, high contrast, text size, empty/error states
- [ ] 8.6 Docs: README, ARCHITECTURE, API, SECURITY_DPDP, PERFORMANCE, PILOT_PLAN, DEMO_SCRIPT, JUDGE_QA, CLAIMS
- [ ] 8.7 Final gate + final commit

### Claim verification
- [x] C1 recommender · [x] C2 calculator · [x] C3 partner map · [x] C4 smart routing · [x] C5 guided path
- [x] C6 voice read-back · [x] C7 speak & scan · [x] C8 rule check · [x] C9 QR + SMS tracking · [x] C10 DigiLocker
- [x] C11 name variations · [ ] C12 shared-phone hygiene · [ ] C13 offline + SMS · [ ] C14 2G/3G · [ ] C15 CSC mode
- [x] C16 pre-check · [x] C17 3-min voice · [x] C18 loan file PDF · [ ] C19 policy dashboard · [ ] C20 open/free/pilot
- [ ] C21 sanction stays with partner

## Phase log

### Phase 1 — Foundation ✅ (2026-09-16)
- Monorepo (pnpm 11 workspaces + Turborepo), shared tsconfig/eslint, cross-platform task runner (`scripts/make.mjs`, Makefile wrapper).
- Core (FastAPI): settings, PII-scrubbing JSON logs, RFC 7807 errors, UUIDv7, tracking-ID check char, AES-256-GCM envelope field encryption, hash-chained audit log (insert-then-chain, verified), OTP auth with lockout, Supabase-shaped JWTs, cache/queue/storage adapters (memory/Redis/ARQ, local-encrypted/S3), circuit breaker + chaos registry, runtime flags.
- DB: all §8 tables; Alembic initial + Postgres-only migration (PostGIS geom, GiST/BRIN/trigram/partial indexes, monthly partitions, RLS policies, append-only audit trigger).
- Gateway (Fastify): JWT verify, per-user + per-phone OTP rate limits, WS hub with channel authz, internal event hook, SMS webhook normalisation, BFF track endpoint.
- Design tokens with WCAG checker (ADR-011); 13-locale catalogues (449 keys) + key/placeholder checker + pseudo-locale (ADR-012/013).
- Web (Next.js 15 + Tailwind v4 + next-intl): httpOnly-cookie sessions via same-origin proxy, per-script Noto fonts, theme/contrast/text-size prefs, language picker, OTP login with demo accounts, officer shell with SANDBOX badges, role guards.
- Docker Compose (postgis, redis, minio, core, ARQ worker, gateway, web, ollama profile) + Dockerfiles; GitHub Actions CI.
- **Gate:** core pytest 11/11, ruff + mypy clean; gateway vitest 7/7 + tsc + eslint clean; i18n + contrast checks pass; `next build` OK (first-load JS 123 kB); `make seed` + `make dev` boot all three services; OTP login verified for citizen, CSC operator, partner officer, admin and policy viewer through web → gateway → core.
- Open items carried forward: `/metrics` endpoint + job modules referenced by worker/compose (Phase 7/8); compose stack not runnable on this machine (no Docker) — Postgres paths to be exercised with portable PostgreSQL+PostGIS binaries in Phase 2.

### Phase 2 — Deterministic core ✅ (2026-09-17)
- Rule engine: whitelisted JSON-Logic twins (Python/TS) sharing one fixture; condition kinds compile to explicit logic + typed sentence params; statuses eligible/ineligible/needs_info; near-miss with "what would change"; next best. Engine coverage 100%, Hypothesis boundaries (₹5,00,000 passes, ₹5,00,001 fails).
- 12 schemes across NSFDC, NBCFDC, NSKFDC, NDFDC (+ MUDRA fallback) covering micro finance, term, education, group and women loans. NBCFDC values verified on nbcfdc.gov.in; the rest flagged `needs_verification` (ADR-016).
- Finance: exact rational arithmetic (ints/BigInt), half-even to the paisa, three moratorium treatments, monthly/quarterly, funding split, affordability with tenure/principal suggestions. 1,000-case golden file matched by the TS twin.
- Routing: 150 fictional partners over 50 district HQs, 6 months of metrics, health score + hard exclusions (low recovery, capacity) shown with reasons, distance decay, geohash-keyed cache; PostGIS KNN verified on portable Postgres 16 + PostGIS 3.6 (ADR-017).
- Web: intake (one question per screen, listen, ₹ words), Rule Check with localized trace and near-miss cards, calculator on-device with schedule chart/table, split bar and compare, partner list + lazy Leaflet map with tile-failure fallback.
- **Gate:** core pytest 96 passed (SQLite) and foundation + persona suites pass on PostGIS; contracts vitest 55 passed; web tsc + eslint clean; Ramesh walked through Rules → Money → Partner in the browser (NSFDC Term Loan, EMI ₹8,440.44, Barmer bank skipped for low recovery).
- Fixed along the way: proxy forwarded stale content-length after decompression; `.env` inline comments were parsed as values (comments now on their own lines).

### 2026-09-17 — Phase 3 complete
- Documents: Laplacian blur / glare / darkness checks, EXIF stripped by re-encode, Aadhaar Verhoeff + last-4 masking (hash only stored), RapidOCR adapter with SANDBOX fallback keyed by file hash, DigiLocker sandbox OAuth pull (clean copy replaces a faded upload).
- Name matching: honorific and relation-word stripping, Devanagari→Latin transliteration with schwa deletion, Jaro-Winkler + phonetic key, DOB / Aadhaar last-4 / father anchors, reasons shown to citizen and officer.
- Readiness 0–100 (presence 50, legibility 20, validity 10, consistency 20); applications draft → consent → submit with tracking ID `SM-<ST>-<YY>-<6><check>`, Ed25519 JWS QR (no PII), status machine (only partner roles decide), hash-chained audit, Hindi/English SMS via console adapter, live tracking timeline (WebSocket + polling), DPDP erase.
- Loan file: fpdf2 + HarfBuzz bilingual PDF with embedded Noto fonts, ~67 KB for Hindi; rows measured before drawing so wrapped labels never overlap.
- **Gate:** core pytest all green; Playwright persona 2 (Ramesh) end to end on PWA passed (43.8 s) including axe checks at four screens.

### 2026-09-17 — Phase 4 complete
- Number words: "dedh lakh", "2.5 lakh", "pachas hazaar", "એક લાખ વીસ હજાર", "साढ़े चार लाख", "₹1,20,000", Indic digits; 29 parametrised cases across 9 languages (ADR-018).
- Slots: rule-based extractor over 13-language lexicons (gender, category, disability, district gazetteer with native names, money-to-field by keyword, education classes/ordinals, SHG, running loans, negation per clause); names taken only from what was said; caste/gender never inferred from names. LLM extractor (Ollama / OpenAI-compatible JSON schema) fills gaps only, capped confidence, redacted prompts (ADR-019).
- Conversation state machine intake → clarify → confirm → done, grouped questions (6 turns fill 13+ fields), correction by naming a field, 12-turn cap hands off to the form.
- Adapters: Bhashini ULCA client (ASR/NMT/TTS), faster-whisper fallback, SANDBOX scripted ASR (ADR-020), glossary-protected translation, TTS clip cache + `cli warm-tts`, device-voice fallback; all behind `guarded()` with chaos toggles.
- Web: /apply/voice with mic (energy VAD, 15 s cap), live "form filling itself" panel, timer and turn counter, demo chips, typed fallback, clarify Yes/No; spoken read-back on the send page with voice confirmation stored as text-only consent evidence (method `voice`).
- Fixes: uvicorn reload on Windows hung on keep-alive connections (`--timeout-graceful-shutdown 3`); storage retries `os.replace` when Windows holds a reader lock; phone from OTP sign-in fills the draft for voice applicants.
- **Gate:** core pytest 147 passed; ruff + mypy clean; i18n 486 keys × 13 locales; contracts 55 + gateway 7 vitest passed; Playwright persona 1 (Gujarati, first turn by microphone, read-back confirmed by voice, submitted) passed in 49.4 s, persona 2 still green.

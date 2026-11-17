# PROGRESS

Re-read this and `CLAUDE.md` at the start of every session.

## Status: Phase (e) complete — ALL PHASES DONE, awaiting final push

## Machine (detected 2026-11-16)
- Apple M4, 10-core CPU, 10-core GPU, 24 GB RAM, macOS 15.7.4, arm64, Metal 3
- python3.11 (/opt/homebrew/bin), python3.12 (~/.local/bin). Default python3 = 3.15.0 (too new for ML wheels).
- ffmpeg 9.0.2 present.
- CORRECTION: CTranslate2 4.9.0 has an experimental Metal (MPS) backend. device=mps ~2x cpu on base/small.

## Whisper benchmark (2026-11-16, M4, faster-whisper 1.2.1 / ct2 4.9.0; 66s clip, int8, beam=1, VAD)
| model  | cpu RTF (x realtime) | mps RTF (x realtime) | notes |
|--------|---------------------|----------------------|-------|
| tiny   | 0.145 (6.9x)        | 0.188 (5.3x)         | cpu wins at tiny; no punctuation/casing |
| base   | 0.588 (1.7x)        | 0.260 (3.8x)         | mps 2.3x faster |
| small  | 0.857 (1.2x)        | 0.630 (1.6x)         | **live pick**: proper punctuation+casing, keeps up with headroom |
| medium | 1.976 (0.5x)        | 1.203 (0.8x)         | slower than realtime even on mps -> offline/final re-transcribe only |
RECOMMEND: live = small on mps int8 (cpu small fallback, 1.2x). Re-transcribe/final quality = medium (offline OK).

## Finished phases
- (none yet) — created CLAUDE.md, PROGRESS.md, .gitignore, THIRD_PARTY_NOTICES.md;
  cloned references to ../reference; machine + licenses + Anthropic models captured.

## Reference licenses (verified 2026-11-16)
- Meetily: MIT. Anarlog: MIT (enterprise/ NOT MIT — avoid). Scriberr: MIT.
- lecture-note-app: PolyForm Noncommercial 1.0.0 — study-only until user approves copying.

## Anthropic models (from claude-api skill, 2026-11-16)
- Live/delta: claude-haiku-4-5 ($1/$5 per 1M; 200K ctx; no thinking/effort).
- Final (default): claude-sonnet-4-6 ($3/$15; 1M ctx, 64K out). Optional: claude-opus-4-8 ($5/$25).
- Prompt caching: ephemeral prefix; min cacheable prefix = 4096 tok on Haiku 4.5. 5-min TTL fits 60s loop.
- Batch API: 50% off, <1h typical (max 24h) — offer as final-pass config option.

## Open decisions / questions for user (asked at this STOP)
- Python version: 3.11 vs 3.12 (3.15 unusable). Leaning 3.11.
- Run Whisper benchmark now? (installs faster-whisper + downloads models ~2 GB, CPU-only on M4).
- Live+final model pair (Haiku 4.5 + Sonnet 4.6 recommended; Opus 4.8 optional for final).
- lecture-note-app (PolyForm Noncommercial): copy code, or study-only/avoid?

## Finished: Phase (a) — skeleton, storage, migrations, library API
- app/: config, db, models (Lecture/TranscriptSegment/Template/Course, all with user_id),
  auth stub (single-user get_current_user), main (app factory + static mount + /health).
- API: lectures (create/list/search/get/rename/retag/delete/notes.md/transcript;
  retranscribe+regenerate stubbed 501), templates CRUD, courses upsert/get (vocab memory).
- Alembic configured; initial migration dfa1b847cecb builds all 4 tables; upgrade/downgrade verified.
- static/index.html bare placeholder lists lectures. .env.example, requirements.txt, pytest.ini.
- Tests: 11 passing (library, templates, courses, migration create-all). uvicorn smoke OK.
- Project venv at .venv (py3.11, gitignored).

## Finished: Phase (b) — audio ingest over WebSocket + upload
- app/audio/wav.py: crash-safe incremental 16kHz mono 16-bit WAV (append PCM, patch
  header on finalize; data_len derived from filesize so nothing is lost on crash).
- app/audio/transcode.py: ffmpeg -> 16kHz mono pcm_s16le for uploads.
- app/api/ws.py: /ws/record WebSocket. start/resume/stop; binary PCM frames appended
  off the event loop (asyncio.to_thread); offset-based resume (server acks only persisted
  bytes -> no loss/no dup); single-writer guard per lecture.
- app/api/upload.py: POST /api/upload (multipart) -> transcode -> lecture (status processing).
- static/worklet.js: AudioWorklet downsamples mic (ctx rate) -> 16kHz int16 PCM.
- static/index.html: recorder (getUserMedia on tap, WS stream, pause/resume, Wake Lock +
  warning, auto-reconnect + resume with client-side unacked buffer) + upload form + library.
- Tests: 19 passing (wav, ws record+resume+error, upload fake+real-ffmpeg+failure).
- Smoke: uploaded jfk.wav (11s) -> 16kHz WAV (176000 frames); assets served.

## Finished: Phase (c) — live transcription with lecture context
- app/transcription/: base (Segment, TranscriptionProvider Protocol, build_initial_prompt),
  faster_whisper_provider (lazy load, mps->cpu fallback, int8/beam1/VAD), fake (tests),
  windowing (silence cut, MIN 10s/MAX 20s), worker (LiveTranscriber: single task, bounded
  deduped queue, per-lecture byte cursor, flat memory, RTF/lag reporting), offline (retranscribe).
- Lecture.transcribed_sec cursor column (migration 5df77ee60cfa).
- ws.py: starts a transcription session per connection, notifies on PCM, flush-on-stop,
  streams {segment}/{status} to client (send-lock serializes with acks), remembers course vocab,
  builds initial_prompt from course/topic/vocab; resume continues from the persisted cursor.
- /retranscribe implemented (offline, runs in a thread). /regenerate still 501 (phase d).
- Tests: 23 passing (windowing, live midstream segment, flush-on-stop, retranscribe; fake provider).
- Smoke: real small/mps transcribed JFK clip correctly with punctuation + timestamps (3 segments).

## Deferred to later phases (noted so they aren't forgotten)
- Opus compression of finished WAV + WAV deletion (storage optimization) -> phase (d)/(e)
  after the final notes pass marks a lecture ready.
- Auth on the WebSocket + rate-limited login -> phase (e).

## Finished: Phase (d) — live delta notes + final adaptive notes
- app/notes/: base (NotesProvider, Usage, SectionPatch, Delta/Final results), document
  (NotesDocument parse/upsert/outline/render, SYSTEM_PROMPT + DEFAULT_TEMPLATE adaptive rules,
  clean_transcript filler strip), pricing (Haiku/Sonnet/Opus + cache rates), fake provider,
  claude_provider (cached system+template prefix, structured-JSON delta, tight max_tokens,
  no thinking, optional Batch API final), engine (NotesEngine).
- NotesEngine: delta loop every interval; reads new transcript via noted_sec cursor; sends
  only outline(headings)+delta; patches returned sections; skips < MIN_NEW_WORDS; dedup via
  content hash (retries/regenerate don't double-spend); per-lecture budget cap pauses live
  notes (transcription continues); logs in/out/cached tokens + est cost per call; final pass
  (strong model) on stop sets status ready; graceful on Claude errors (keep last good notes).
- Lecture cursors/accounting: noted_sec, final_hash, notes_paused (migration e9b25cea3297);
  TypedNote table (typed high-priority notes while recording).
- ws.py: notes loop task per connection, typed-note ingest, flush+final on stop, streams
  segment/notes/notes_cost/notes_paused/notes_final; send-lock serializes everything.
- /regenerate implemented (final pass over saved transcript, dedup). index.html now shows
  live transcript + notes + cost + a typed-note box.
- Tests: 33 passing incl. 3-HOUR FLAT-COST PROOF (180 updates: 1 call/update, bounded delta,
  linear tokens, memory < 80MB, final once), dedup, budget pause, document model.
- Smoke: real whisper + keyless graceful notes degradation (HTTP 200, no crash, no spend).

## NOT yet tested: real Claude notes (needs ANTHROPIC_API_KEY; would spend credits).
  Logic fully covered by fake-provider tests. To test real: set key in .env and record/regenerate.

## Finished: Phase (e) — auth, backup/restore, Opus, Docker, README
- app/auth.py: one-password -> HMAC-signed session cookie; get_current_user dependency
  protects every router AND the WebSocket; per-IP failed-login rate limit.
- app/api/auth_routes.py: /api/login, /api/logout, /api/me.
- Opus compression on stop (WAV -> Opus 24k, delete WAV); offline retranscribe decodes
  Opus->temp WAV; config COMPRESS_AUDIO/OPUS_BITRATE/AUDIO_RETENTION_DAYS (startup cleanup).
- app/backup.py: create/restore (db + audio + notes.md tar.gz), delete_old_audio; CLI
  (python -m app.backup create|restore). GET /api/backup download endpoint.
- Dockerfile + .dockerignore (ffmpeg, volumes for data + model cache; CPU note for Linux).
- README.md: setup (Docker + no-Docker), .env, model benchmark table, HTTPS via
  Cloudflare Tunnel/Tailscale, keep-awake (caffeinate), usage, API, backup/restore, tests.
- static/index.html: login gate.
- Tests: 40 passing (auth incl. WS cookie + rate limit, backup roundtrip + endpoint,
  Opus compression). Smoke: auth-gated upload/retranscribe/backup + CLI backup/restore.

## PROJECT COMPLETE — all phases (a)-(e) done. 40 tests pass.
- Still untested: the REAL Claude notes path (needs ANTHROPIC_API_KEY; would spend credits).
  Logic fully covered by fake-provider tests incl. the 3-hour flat-cost proof.
  To validate real notes: put the key in .env and record (or /regenerate) — a few cents.

## iPhone recording still needs HTTPS (Cloudflare Tunnel/Tailscale; README in phase e).
  Local http://localhost:8000 works (secure context).

## Token / storage estimates (fill in at each STOP)
- Claude tokens per lecture hour: TBD
- Storage per lecture hour: WAV ~115 MB/hr (transient) -> Opus ~7-11 MB/hr (kept)

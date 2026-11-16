# PROGRESS

Re-read this and `CLAUDE.md` at the start of every session.

## Status: Phase (b) complete — awaiting push before Phase (c)

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

## What comes next
- Phase (c): live transcription with lecture context (faster-whisper small/mps worker,
  VAD rolling windows every 10-15s, push timestamped segments over WS, report RTF/lag;
  wire the /retranscribe stub).
- Then (d) delta+final notes, (e) auth/backup/Docker/README.

## iPhone recording not yet testable over the internet
- getUserMedia needs HTTPS; expose via Cloudflare Tunnel/Tailscale (README in phase e).
  Local laptop testing works at http://localhost:8000 (secure context).

## Token / storage estimates (fill in at each STOP)
- Claude tokens per lecture hour: TBD
- Storage per lecture hour: WAV ~115 MB/hr (transient) -> Opus ~7-11 MB/hr (kept)

# autolect — project rules (re-read at the start of every session)

This file exists so the rules below survive across sessions. Re-read this and
`PROGRESS.md` at the start of every session. The three sections reproduced
verbatim (GIT RULES, OPTIMIZATION, OUT OF SCOPE) are the user's words and must
not be paraphrased or relaxed.

---

## SUPER IMPORTANT: GIT RULES. READ FIRST.
- NEVER run `git push`, under any circumstances, even if I seem to ask casually
  or a step appears to need it. I always push the code myself.
- Do not commit either unless I explicitly tell you to.
- STOP at the end of every phase listed under "How to work" and at any other
  important milestone. At each stop, give me:
  1. a summary of what changed (files added, changed, removed, and why),
  2. what you tested and what is untested,
  3. estimated Claude tokens per lecture hour and MB of storage per lecture hour,
  4. a suggested commit message.
  Then wait. Do not continue until I say I have pushed.
- Never force anything, never rewrite history, never touch remotes.
- Your very first action: create CLAUDE.md containing these git rules, the
  optimization rules and the out-of-scope list below, word for word, so they
  survive across sessions. Also create PROGRESS.md and update it at every stop
  with finished phases, open decisions and what comes next. Re-read both files
  at the start of every session.

---

## OPTIMIZATION IS MANDATORY (lectures run up to 3 hours)
Treat Claude API credits, disk space and CPU as scarce. Examples of what I expect;
propose more:

Claude API credits
- Live updates are deltas, never rewrites. Send only the transcript added since
  the last update plus a compact outline of the existing notes (headings only).
  Claude returns only new or changed sections, and the server patches them in.
  Output tokens must not grow with lecture length.
- Skip the update entirely when fewer than N new words arrived (breaks, silence).
- Update interval is configurable (default 60s), so I can set 2-5 minutes.
- Use a cheap, fast model for live updates and a stronger model only for the one
  final pass. Both model IDs come from .env.
- Use prompt caching: system prompt and notes template go first as a stable,
  cached prefix.
- Offer the Batch API for the final pass as a config option if the docs confirm
  it is cheaper and I'm willing to wait.
- Strip timestamps and filler from the transcript before sending. Set tight
  max_tokens. No extended thinking on live updates.
- Never call Claude twice for the same input: hash transcript plus template and
  reuse stored results. Retries must not double-spend.
- Log input, output and cached tokens for every call, and store totals and the
  estimated cost per lecture.
- Per-lecture budget cap in .env: when hit, pause live notes, keep transcribing,
  and tell me.

Storage
- Raw 16 kHz mono WAV is about 115 MB per hour. After the lecture ends and the
  transcript is verified, compress to Opus at about 16-24 kbps with ffmpeg
  (roughly 7-11 MB per hour), then delete the WAV.
- Config options: auto-delete audio after N days, or keep transcript and notes only.
- Store transcript segments as compact rows. No word-level timestamps unless needed.
- Show disk usage per lecture and in total in the library.

Recording and transcription
- Use VAD so silence is never transcribed or sent to Claude.
- Transcribe each second of audio once: minimal overlap, no re-running old windows.
- Live settings tuned for speed: int8 quantization, beam size 1, smallest model
  that is accurate enough on this machine.
- One transcription worker with a bounded queue; memory use must stay flat for
  3 hours. Report real-time factor and lag.

Proof
- A test that simulates a 3-hour lecture with fake providers and asserts that
  per-update payload size, Claude call count and memory do not grow with length.

---

## Out of scope: do not build
- Chat with the lecture or any Q&A feature.
- Accounts, sign-up, multi-user features (only keep the door open, see Library).
- Styling, CSS frameworks, JS frameworks, a native mobile app.
- Practice questions, flashcards, sharing, cloud sync.
- Any feature not listed in this prompt. Suggest ideas at a STOP; don't build them.

---

## How to work (phases — STOP after each)
1. Create CLAUDE.md and PROGRESS.md. Clone and skim the reference projects. Detect
   and benchmark this machine. Ask clarifying questions, show a short plan, file
   layout and reuse list, and wait for approval.
2. Build in phases, running tests at the end of each. Each phase ends with a
   mandatory STOP:
   (a) project skeleton, .gitignore, storage, migrations and library API
   (b) audio ingest over WebSocket, plus file upload
   (c) live transcription with lecture context
   (d) live delta notes and final notes with adaptive formatting
   (e) auth, backup and restore, Docker, README

REMINDER: never push, never commit unless told. Stop after every phase and wait.

---

## Stack (summary — see original brief for full detail)
- Python 3.11+, FastAPI, uvicorn, SQLite via SQLModel, Alembic, pytest.
- Transcription: local faster-whisper behind a `TranscriptionProvider` interface.
  Model/device/compute type from .env. NOTE: CTranslate2 4.9 has an EXPERIMENTAL
  Metal (MPS) backend on Apple Silicon — device=mps is ~2x faster than cpu on
  base/small. Default device=mps, compute_type=int8, with cpu fallback in .env.
- Notes: Claude API via official `anthropic` SDK behind a `NotesProvider`
  interface. Model IDs/keys from .env. Check Anthropic docs for current model IDs,
  caching and pricing.
- Frontend: one static index.html, vanilla JS, no framework/build step, served by
  FastAPI. Barest functional HTML.
- Audio: AudioWorklet -> 16 kHz mono 16-bit PCM over WebSocket (NOT MediaRecorder
  timeslices on iOS). HTTPS + getUserMedia from a tap. Wake Lock while recording.
- Auth: one password from .env -> session cookie, protects everything incl. the
  WebSocket. Rate-limit login.
- Every table carries user_id; Alembic migrations from the start; auth in one
  dependency so accounts can be added later.

## Reference projects (cloned to ../reference, OUTSIDE this repo)
- Meetily (check license): live Whisper pipeline, VAD/chunking, summary prompts,
  provider abstraction. (Rust -> port logic to Python.)
- Anarlog (check license; enterprise/ folder is NOT MIT, do not use): merge typed
  notes with transcript, note templates, user-owned Markdown notes. (Rust.)
- Scriberr (check license): transcription job handling, custom prompt templates,
  REST API design, library/transcript storage. (Go.)
- lecture-note-app (reported PolyForm Noncommercial — CONFIRM and ASK before
  copying): FastAPI + faster-whisper, notes every minute. Study its live loop.
- Record every copied/ported piece in THIRD_PARTY_NOTICES.md.

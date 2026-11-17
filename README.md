# autolect

Self-hosted lecture notes. Press record on your phone, watch a live transcript
and live-updating notes during the lecture, and get polished Markdown notes saved
to a library when you stop. Local Whisper for transcription, Claude for notes.

- **Transcription:** local [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
  behind a `TranscriptionProvider` interface (model/device from `.env`).
- **Notes:** Claude via the official `anthropic` SDK behind a `NotesProvider`
  interface — cheap/fast model for live delta updates, stronger model for the
  final pass. Model IDs from `.env`.
- **Frontend:** one static `index.html` with vanilla JS. No framework, no build step.
- **Storage:** SQLite via SQLModel, Alembic migrations, audio compressed to Opus.

---

## Requirements

- Python 3.11+ (3.12 works). **Not** 3.13+ for the ML wheels.
- `ffmpeg` on PATH (upload transcode + Opus compression).
- An Anthropic API key for notes (transcription works without one).

## Setup (no Docker)

```sh
python3.11 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then edit: set APP_PASSWORD, SESSION_SECRET, ANTHROPIC_API_KEY
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000, log in with `APP_PASSWORD`, and record.

> First live-notes run downloads the Whisper `small` model (~480 MB) once; it is
> cached afterward.

## Setup (Docker)

```sh
docker build -t autolect .
docker run --rm -p 8000:8000 --env-file .env \
  -v autolect-data:/app/data \
  -v autolect-models:/root/.cache/huggingface \
  autolect
```

The named volumes persist the database/audio and the Whisper model cache. Inside
Linux containers Whisper runs on CPU — set `WHISPER_DEVICE=cpu` in `.env`.

## Configuration

All config is in `.env` (see `.env.example`). Key settings:

| Setting | Meaning |
|---|---|
| `APP_PASSWORD` | the single login password |
| `SESSION_SECRET` | signs the session cookie — use a long random string |
| `ANTHROPIC_API_KEY` | Claude key for notes |
| `LIVE_MODEL` / `FINAL_MODEL` | `claude-haiku-4-5` / `claude-sonnet-4-6` by default |
| `NOTES_UPDATE_INTERVAL_SEC` | live-notes cadence (default 60; try 120–300) |
| `MIN_NEW_WORDS_FOR_UPDATE` | skip an update with fewer new words (silence/breaks) |
| `PER_LECTURE_BUDGET_USD` | pause live notes when hit (transcription continues) |
| `WHISPER_MODEL` / `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `small` / `mps` / `int8` |
| `COMPRESS_AUDIO` / `OPUS_BITRATE` | compress WAV → Opus after notes (default on, 24k) |
| `AUDIO_RETENTION_DAYS` | 0 = keep forever; else delete old audio at startup |
| `USE_BATCH_API_FOR_FINAL` | use the 50%-cheaper Batch API for the final pass |

### Choosing a Whisper model

This machine (Apple M4) was benchmarked at setup (faster-whisper, int8, beam 1,
VAD). Real-time factor = processing ÷ audio (lower is better; <1 = faster than
real time):

| model | CPU (×realtime) | MPS/GPU (×realtime) | notes |
|---|---|---|---|
| tiny | 6.9× | 5.3× | no casing/punctuation |
| base | 1.7× | 3.8× | no casing/punctuation |
| **small** | 1.2× | **1.6×** | **default** — correct casing/punctuation |
| medium | 0.5× (too slow) | 0.8× (too slow) | offline re-transcription only |

Default: `small` on `mps`. If the experimental Metal backend misbehaves, set
`WHISPER_DEVICE=cpu` (small still runs ~1.2× real time).

## Exposing it to your phone (HTTPS)

Microphone capture (`getUserMedia`) requires a **secure context** — HTTPS or
`localhost`. To record from your iPhone, expose the laptop over HTTPS:

**Cloudflare Tunnel** (quick, public URL):
```sh
cloudflared tunnel --url http://localhost:8000
```
Open the printed `https://<random>.trycloudflare.com` on your phone.

**Tailscale** (private, with HTTPS):
```sh
tailscale up
tailscale serve https / http://localhost:8000
```
Open the `https://<machine>.<tailnet>.ts.net` URL on your phone (same tailnet).

Either way, log in with `APP_PASSWORD` first.

### Keeping the laptop awake during a lecture

macOS: run the server under `caffeinate` so it doesn't sleep:
```sh
caffeinate -s ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```
On the phone, keep Safari in the foreground — the app requests a screen Wake
Lock, but locking the phone or switching apps stops capture. The recorder buffers
and auto-reconnects across brief network drops and resumes the same lecture.

## Recording, uploading, library

- **Record:** fill in title/course/vocabulary, tap **Start**, allow the mic. Live
  transcript and notes appear as you speak. Type high-priority notes in the box;
  they're folded into the notes. **Stop** runs the final pass and saves.
- **Upload** an existing recording (e.g. an iPhone Voice Memo `.m4a`) — it runs
  through the same transcription/notes pipeline.
- **Library** lists saved lectures. REST API under `/api` (all require login):

| Endpoint | |
|---|---|
| `GET /api/lectures?q=&course=` | list / search (title, course, full-text transcript) |
| `GET /api/lectures/{id}` | details |
| `PATCH /api/lectures/{id}/rename` · `/retag` | rename / re-tag |
| `DELETE /api/lectures/{id}` | delete |
| `GET /api/lectures/{id}/notes.md` · `/transcript` | downloads |
| `POST /api/lectures/{id}/retranscribe` | re-transcribe from saved audio |
| `POST /api/lectures/{id}/regenerate` | regenerate notes from saved transcript |
| `GET /api/backup` | download a full-library archive |
| `POST /api/upload` | upload a recording |
| `POST /api/login` · `/logout` · `GET /api/me` | auth |

Templates (`/api/templates`) and per-course vocabulary (`/api/courses`) let you
save multiple notes templates and remember vocabulary per course.

## Backup & restore

```sh
./.venv/bin/python -m app.backup create [archive.tar.gz]   # db + audio + notes.md
./.venv/bin/python -m app.backup restore <archive.tar.gz>  # replaces db + audio
```
Or download an archive from `GET /api/backup` in the browser.

## Tests

```sh
./.venv/bin/python -m pytest
```
Tests use fake transcription/notes providers — they never hit the real Claude API
or download models. They cover the WebSocket session lifecycle, reconnect/resume,
the delta note-update loop (including a 3-hour flat-cost/flat-memory proof), file
upload, backup/restore, auth, and every library endpoint.

## How it keeps cost and storage down

- Live notes are **deltas**: each update sends only the new transcript plus the
  existing notes' headings; Claude returns only changed sections, patched in —
  output does not grow with lecture length.
- Updates are skipped below a word threshold; identical inputs are hashed and
  never re-sent (retries don't double-spend); a per-lecture budget cap pauses
  live notes while transcription continues.
- The system prompt + template are a cached prefix; live uses a cheap model, the
  final pass a stronger one (optionally via the 50%-cheaper Batch API).
- Audio is captured as 16 kHz mono WAV (~115 MB/hr), then compressed to Opus
  (~7–11 MB/hr) after the transcript is produced; the WAV is deleted.

# PROGRESS

Re-read this and `CLAUDE.md` at the start of every session.

## Status: Phase 1 (setup) — awaiting approval of plan before building

## Machine (detected 2026-11-16)
- Apple M4, 10-core CPU, 10-core GPU, 24 GB RAM, macOS 15.7.4, arm64, Metal 3
- python3.11 (/opt/homebrew/bin), python3.12 (~/.local/bin). Default python3 = 3.15.0 (too new for ML wheels).
- ffmpeg 9.0.2 present.
- KEY: faster-whisper/CTranslate2 is CPU-only on Apple Silicon (no Metal). device=cpu, compute_type=int8.

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

## What comes next
1. Clone + skim references, record licenses in THIRD_PARTY_NOTICES.md.
2. Benchmark Whisper models on this M4; show real-time factors; recommend one.
3. Get plan/file-layout/reuse-list approved.
4. Phase (a): skeleton, .gitignore, storage, migrations, library API.

## Token / storage estimates (fill in at each STOP)
- Claude tokens per lecture hour: TBD
- Storage per lecture hour: WAV ~115 MB/hr (transient) -> Opus ~7-11 MB/hr (kept)

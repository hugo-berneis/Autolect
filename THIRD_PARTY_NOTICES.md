# Third-Party Notices

This project ports/adapts logic from the reference projects below. Each copied or
ported piece will be recorded here with source repo, file, and license as it is
added. Reference repos live OUTSIDE this repo (in `../reference`) and are not
redistributed here.

## Reference projects and licenses (verified 2026-11-16)

| Project | Repo | License | Usage |
|---|---|---|---|
| Meetily | github.com/Zackriya-Solutions/meetily | MIT (© 2024 Zackriya Solutions) | Live Whisper pipeline, VAD/chunking, summary prompts, provider abstraction |
| Anarlog | github.com/fastrepl/anarlog | MIT (© 2023–present Fastrepl, Inc.) | Typed-notes↔transcript merge, note templates, Markdown notes. **`enterprise/` folder is NOT MIT — not used.** |
| Scriberr | github.com/rishikanthc/Scriberr | MIT (© 2025 Scriberr) | Transcription job handling, custom prompt templates, REST API design, library/transcript storage |
| lecture-note-app | github.com/mrgutierrezmario/lecture-note-app | **PolyForm Noncommercial 1.0.0** (© 2026 M.G. Network and Technology Solutions) | **Noncommercial only.** Awaiting user decision before copying any code; study-only until then. |

MIT license text requires the copyright notice and permission notice be retained
with any substantial portions copied. When MIT code is ported, the relevant
notice will be reproduced alongside the entry below.

## Ported pieces

None. The reference projects were studied for approach (VAD/rolling-window
transcription, delta-notes loop, REST/library design, note templates), but all
code in this repository — including the notes prompts and templates — was written
originally for this project. No source code was copied or ported, so no MIT
copyright notices need reproducing here. lecture-note-app (PolyForm Noncommercial)
was study-only and nothing from it was used.

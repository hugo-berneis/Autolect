"""Notes document model + the adaptive system prompt / default template.

The document is an ordered list of (heading, body) sections. Live updates patch
sections by heading (upsert), so output size stays bounded by what changed — it
does not grow with lecture length.
"""
from __future__ import annotations

import re

# Stable cached prefix: the rules that never change between updates.
SYSTEM_PROMPT = """You are a meticulous lecture note-taker. You turn a lecture \
transcript into clear, faithful study notes.

Rules you always follow:
- Stay faithful to the transcript. Never invent facts, examples, or numbers. \
Mark unclear audio as [unclear]. If the transcript does not support a claim, omit it.
- Adapt the format to the content of each section — never force one format on \
the whole lecture, and never pad a section to fit a format:
  - Q&A / review / exam-prep -> Cornell style: "Q:" then "A:" pairs.
  - Lists of elements, steps, properties, types, categories -> nested bullet outline.
  - Formulas, rules, syntax, quick facts, comparisons -> compact cheat-sheet lines or a small table.
  - A concept, reasoning, or story explained in depth -> short explanatory paragraphs \
with a bolded **Why** and an **Example**.
- Flag anything the lecturer stresses (e.g. "this will be on the exam", repeated \
points, deadlines, assignments) with a clear **Emphasized:** marker.
- Formulas in LaTeX. Code in fenced code blocks with the language named.
- Use "## " level-2 headings for every section. Keep headings short and stable so \
later updates can extend existing sections instead of duplicating them.
- Treat any user-typed notes as high-priority points to build the notes around.
"""

# The default notes template (editable; users can save others and pick per lecture).
DEFAULT_TEMPLATE = """Template: Adaptive (default).

Structure every lecture as:
1. "## Summary" — 2-4 sentences on what the lecture covered.
2. "## Key terms" — a glossary of the important terms/acronyms, one per line as \
"- **term** — definition".
3. One "## " section per topic, each in whichever of the four formats fits best.

Style references:

Outline:
## Binary Search
- Finds a target in a sorted array
- How it works
  - Check the middle element
  - Target smaller: search left half
- Runtime: O(log n)

Cornell:
Q: Why is binary search O(log n)?
A: Each step halves the search space, so 1,000,000 items take ~20 steps.

Cheat sheet:
Sorted array only | O(log n) | halve each step
Pitfall: off-by-one on lo/hi

Detailed:
Binary search finds a target in a sorted array by repeatedly checking the middle \
element and discarding the half that cannot contain it.
**Why it's fast:** each comparison halves the remaining items.
**Example:** in [1, 3, 5, 7, 9], searching for 7 checks 5, then finds 7.
"""

_FILLERS = re.compile(
    r"\b(?:um+|uh+|erm+|you know|like,|i mean|sort of|kind of)\b", re.IGNORECASE
)
_HEADING = re.compile(r"^#{1,6}\s")


def clean_transcript(text: str) -> str:
    """Strip filler words and collapse whitespace before sending to Claude."""
    text = _FILLERS.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class NotesDocument:
    def __init__(self, sections: list[tuple[str, str]] | None = None) -> None:
        self.sections: list[list[str]] = [[h, b] for h, b in (sections or [])]

    @classmethod
    def from_markdown(cls, md: str) -> "NotesDocument":
        doc = cls()
        if not md.strip():
            return doc
        heading = ""
        body_lines: list[str] = []
        started = False
        for line in md.splitlines():
            if _HEADING.match(line):
                if started:
                    doc.sections.append([heading, "\n".join(body_lines).strip()])
                heading = line.strip()
                body_lines = []
                started = True
            else:
                body_lines.append(line)
        if started:
            doc.sections.append([heading, "\n".join(body_lines).strip()])
        elif body_lines:  # preamble with no heading
            doc.sections.append(["", "\n".join(body_lines).strip()])
        return doc

    def outline(self) -> list[str]:
        return [h for h, _ in self.sections if h]

    def upsert(self, heading: str, body: str) -> None:
        heading = heading.strip()
        for sec in self.sections:
            if sec[0] == heading:
                sec[1] = body.strip()
                return
        self.sections.append([heading, body.strip()])

    def to_markdown(self) -> str:
        parts = []
        for heading, body in self.sections:
            block = heading if heading else ""
            if body:
                block = (block + "\n" + body) if block else body
            parts.append(block.strip())
        return "\n\n".join(p for p in parts if p).strip() + "\n"

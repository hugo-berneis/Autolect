"""Notes provider interface and result/usage types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class SectionPatch:
    heading: str
    body: str


@dataclass
class DeltaResult:
    sections: list[SectionPatch] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""


@dataclass
class FinalResult:
    markdown: str = ""
    usage: Usage = field(default_factory=Usage)
    model: str = ""


class NotesProvider(Protocol):
    def update_notes(
        self,
        *,
        system: str,
        template: str,
        outline: list[str],
        transcript_delta: str,
        typed_notes: str = "",
    ) -> DeltaResult:
        """Return only new/changed sections for the transcript added since the
        last update (cheap/fast live model)."""
        ...

    def final_notes(
        self,
        *,
        system: str,
        template: str,
        transcript: str,
        typed_notes: str = "",
    ) -> FinalResult:
        """Produce the complete polished notes from the full transcript
        (stronger model, one pass)."""
        ...

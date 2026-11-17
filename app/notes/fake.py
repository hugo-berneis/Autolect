"""Deterministic notes provider for tests — records inputs so the 3-hour
flat-cost proof can assert that per-update payload size stays bounded."""
from __future__ import annotations

from .base import DeltaResult, FinalResult, SectionPatch, Usage


class FakeNotesProvider:
    def __init__(self) -> None:
        self.update_calls = 0
        self.final_calls = 0
        self.delta_chars: list[int] = []
        self.outline_lens: list[int] = []

    def update_notes(
        self,
        *,
        system: str,
        template: str,
        outline: list[str],
        transcript_delta: str,
        typed_notes: str = "",
    ) -> DeltaResult:
        self.update_calls += 1
        self.delta_chars.append(len(transcript_delta))
        self.outline_lens.append(len(outline))
        # Simulate adaptive notes: a new topic section every ~10 updates, so the
        # document grows slowly while each update returns O(1) sections.
        topic = self.update_calls // 10
        sections = [
            SectionPatch(f"## Topic {topic}", f"- point from update {self.update_calls}")
        ]
        return DeltaResult(
            sections=sections,
            usage=Usage(input_tokens=200, output_tokens=60),
            model="fake-live",
        )

    def final_notes(
        self,
        *,
        system: str,
        template: str,
        transcript: str,
        typed_notes: str = "",
    ) -> FinalResult:
        self.final_calls += 1
        md = "## Summary\nFinal notes.\n\n## Key terms\n- **term** — definition\n"
        return FinalResult(
            markdown=md, usage=Usage(input_tokens=500, output_tokens=120), model="fake-final"
        )

"""Claude notes provider (official anthropic SDK).

Optimizations per the project rules:
- system + template go first as a stable, cache_control'd prefix.
- live deltas send only the headings outline + the new transcript, and ask for
  only new/changed sections (structured JSON) -> output does not grow with length.
- tight max_tokens, no extended thinking on live updates.
- optional Batch API for the final pass (50% cheaper) when configured.
"""
from __future__ import annotations

import json
from typing import Optional

from .base import DeltaResult, FinalResult, SectionPatch, Usage

_DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["heading", "body"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


def _usage(resp) -> Usage:
    u = resp.usage
    return Usage(
        input_tokens=getattr(u, "input_tokens", 0) or 0,
        output_tokens=getattr(u, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0,
    )


def _first_text(content) -> str:
    for block in content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""


class ClaudeNotesProvider:
    def __init__(
        self,
        live_model: str = "claude-haiku-4-5",
        final_model: str = "claude-sonnet-4-6",
        api_key: str = "",
        max_tokens_live: int = 1024,
        max_tokens_final: int = 8000,
        use_batch_for_final: bool = False,
    ) -> None:
        self.live_model = live_model
        self.final_model = final_model
        self.api_key = api_key
        self.max_tokens_live = max_tokens_live
        self.max_tokens_final = max_tokens_final
        self.use_batch_for_final = use_batch_for_final
        self._client = None

    def _client_(self):
        if self._client is None:
            import anthropic  # lazy: not needed when the fake provider is used

            self._client = anthropic.Anthropic(api_key=self.api_key or None)
        return self._client

    @staticmethod
    def _system_blocks(system: str, template: str) -> list[dict]:
        # cache_control on the last (template) block caches system+template together.
        return [
            {"type": "text", "text": system},
            {"type": "text", "text": template, "cache_control": {"type": "ephemeral"}},
        ]

    def update_notes(
        self,
        *,
        system: str,
        template: str,
        outline: list[str],
        transcript_delta: str,
        typed_notes: str = "",
    ) -> DeltaResult:
        client = self._client_()
        outline_text = "\n".join(outline) if outline else "(no notes yet)"
        user = (
            "Existing notes outline (headings only):\n"
            f"{outline_text}\n\n"
            "New transcript since the last update:\n"
            f"{transcript_delta}\n"
        )
        if typed_notes:
            user += f"\nHigh-priority notes the user typed just now:\n{typed_notes}\n"
        user += (
            "\nReturn ONLY the new or changed sections for this new material, as JSON. "
            "Reuse an existing heading verbatim to extend/replace that section; use a "
            "new heading for a new topic. Do not restate unchanged sections."
        )
        resp = client.messages.create(
            model=self.live_model,
            max_tokens=self.max_tokens_live,
            system=self._system_blocks(system, template),
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": _DELTA_SCHEMA}},
        )
        sections: list[SectionPatch] = []
        try:
            data = json.loads(_first_text(resp.content) or "{}")
            for s in data.get("sections", []):
                sections.append(SectionPatch(s["heading"], s["body"]))
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return DeltaResult(sections=sections, usage=_usage(resp), model=self.live_model)

    def final_notes(
        self,
        *,
        system: str,
        template: str,
        transcript: str,
        typed_notes: str = "",
    ) -> FinalResult:
        user = (
            "Full lecture transcript:\n"
            f"{transcript}\n"
        )
        if typed_notes:
            user += f"\nHigh-priority notes the user typed during the lecture:\n{typed_notes}\n"
        user += "\nProduce the complete, polished notes now, following the template."
        params = dict(
            model=self.final_model,
            max_tokens=self.max_tokens_final,
            system=self._system_blocks(system, template),
            messages=[{"role": "user", "content": user}],
        )
        if self.use_batch_for_final:
            return self._final_via_batch(params)
        resp = self._client_().messages.create(**params)
        return FinalResult(
            markdown=_first_text(resp.content).strip(),
            usage=_usage(resp),
            model=self.final_model,
        )

    def _final_via_batch(self, params: dict) -> FinalResult:
        import time

        from anthropic.types.message_create_params import (
            MessageCreateParamsNonStreaming,
        )
        from anthropic.types.messages.batch_create_params import Request

        client = self._client_()
        batch = client.messages.batches.create(
            requests=[
                Request(
                    custom_id="final",
                    params=MessageCreateParamsNonStreaming(**params),
                )
            ]
        )
        while True:
            b = client.messages.batches.retrieve(batch.id)
            if b.processing_status == "ended":
                break
            time.sleep(30)
        for result in client.messages.batches.results(batch.id):
            if result.result.type == "succeeded":
                msg = result.result.message
                return FinalResult(
                    markdown=_first_text(msg.content).strip(),
                    usage=_usage(msg),
                    model=self.final_model,
                )
        return FinalResult(markdown="", usage=Usage(), model=self.final_model)

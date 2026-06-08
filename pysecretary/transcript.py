from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Iterable
from typing import Protocol

from .llm import LLMClient


THINK_BLOCK_RE = re.compile(r"<think>(?P<thought>.*?)</think>", re.IGNORECASE | re.DOTALL)
OPEN_THINK_RE = re.compile(r"<think>(?P<thought>.*)$", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ThoughtSplit:
    final_text: str
    thoughts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptMergeResult:
    smoothed_text: str
    feedback: list[str] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    context_summary: str = ""
    context_action: str = "continue"


@dataclass(frozen=True)
class TranscriptSection:
    turn_id: str
    sequence: int
    text: str
    captured_at: float
    transcribed_at: float
    duration_seconds: float
    speech_seconds: float
    peak_level: float

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "section": self.sequence,
            "turn_id": self.turn_id,
            "captured_at": round(self.captured_at, 3),
            "transcribed_at": round(self.transcribed_at, 3),
            "duration_seconds": round(self.duration_seconds, 3),
            "speech_seconds": round(self.speech_seconds, 3),
            "peak_level": round(self.peak_level, 4),
            "raw_text": self.text,
        }


class TranscriptMerger(Protocol):
    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        ...


def split_thought_text(text: str) -> ThoughtSplit:
    thoughts: list[str] = []

    def replace_complete(match: re.Match[str]) -> str:
        thought = match.group("thought").strip()
        if thought:
            thoughts.append(thought)
        return ""

    without_complete = THINK_BLOCK_RE.sub(replace_complete, text)
    open_match = OPEN_THINK_RE.search(without_complete)
    if open_match:
        thought = open_match.group("thought").strip()
        if thought:
            thoughts.append(thought)
        without_complete = without_complete[: open_match.start()]

    return ThoughtSplit(final_text=without_complete.strip(), thoughts=thoughts)


def parse_merge_response(response_text: str) -> TranscriptMergeResult:
    split = split_thought_text(response_text)
    payload = _extract_json_object(split.final_text)
    if payload is None:
        return TranscriptMergeResult(
            smoothed_text=split.final_text,
            feedback=[],
            thoughts=split.thoughts,
        )

    smoothed_text = str(
        payload.get("smoothed_text")
        or payload.get("updated_text")
        or payload.get("text")
        or ""
    ).strip()
    feedback = _normalize_feedback(payload.get("feedback") or payload.get("notes") or [])
    thoughts = list(split.thoughts)
    thoughts.extend(_normalize_feedback(payload.get("thoughts") or []))
    context_summary = str(payload.get("context_summary") or "").strip()
    context_action = _normalize_context_action(payload.get("context_action"))

    return TranscriptMergeResult(
        smoothed_text=smoothed_text,
        feedback=feedback,
        thoughts=thoughts,
        context_summary=context_summary,
        context_action=context_action,
    )


class LLMTranscriptMerger:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        """Clean the new sections against the editable transcript tail.

        ``existing_smoothed_text`` is the small re-editable tail of the transcript the
        controller chose (see ``split_recent_tail``); everything older is already settled.
        The model returns, per ``context_action``: on ``continue`` the corrected tail merged
        with the new sections; on ``paragraph``/``renew`` only the cleaned new sections. The
        controller decides how to splice the result back in.
        """
        new_raw_text = format_transcript_sections_for_prompt(new_raw_sections)
        response_text = self.llm.merge_transcript_context(
            existing_smoothed_text=existing_smoothed_text,
            new_raw_text=new_raw_text,
            recent_raw_context=recent_raw_context,
            current_context_summary=current_context_summary,
            prior_transcript_was_reduced=False,
        )
        return parse_merge_response(response_text)


def format_transcript_sections_for_prompt(sections: Iterable[TranscriptSection]) -> str:
    payload = {
        "transcript_sections": [section.to_prompt_dict() for section in sections],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _extract_json_object(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_feedback(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_context_action(value: object) -> str:
    action = str(value or "continue").strip().lower()
    if action in {"renew", "new", "new_conversation", "reset", "new_topic"}:
        return "renew"
    if action in {"paragraph", "new_paragraph", "new_para", "newline", "break"}:
        return "paragraph"
    return "continue"

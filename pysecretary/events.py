from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AssistantEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.event_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class AssistantCommand:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload}


@dataclass
class PrototypeState:
    running: bool = False
    status: str = "stopped"
    raw_transcripts: list[dict[str, Any]] = field(default_factory=list)
    discarded_turns: list[dict[str, Any]] = field(default_factory=list)
    discarded_transcriptions: list[dict[str, Any]] = field(default_factory=list)
    smoothed_text: str = ""
    committed_text: str = ""
    context_summary: str = ""
    context_action: str = "continue"
    feedback: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    last_audio_level: float = 0.0
    audio_detected: bool = False
    in_speech_turn: bool = False
    queue_depths: dict[str, int] = field(
        default_factory=lambda: {"audio_turn_queue": 0, "raw_transcript_queue": 0}
    )
    worker_options: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "status": self.status,
            "raw_transcripts": list(self.raw_transcripts),
            "discarded_turns": list(self.discarded_turns),
            "discarded_transcriptions": list(self.discarded_transcriptions),
            "smoothed_text": self.smoothed_text,
            "committed_text": self.committed_text,
            "context_summary": self.context_summary,
            "context_action": self.context_action,
            "feedback": list(self.feedback),
            "thoughts": list(self.thoughts),
            "errors": list(self.errors),
            "events": list(self.events),
            "last_audio_level": self.last_audio_level,
            "audio_detected": self.audio_detected,
            "in_speech_turn": self.in_speech_turn,
            "queue_depths": dict(self.queue_depths),
            "worker_options": dict(self.worker_options),
        }


def make_event(event_type: str, **payload: Any) -> AssistantEvent:
    return AssistantEvent(type=event_type, payload=payload)


def reduce_prototype_state(state: PrototypeState, event: AssistantEvent) -> PrototypeState:
    event_record = event.to_dict()
    state.events.append(event_record)
    state.events = state.events[-200:]

    if event.type == "AssistantStateChanged":
        status = str(event.payload.get("status", state.status))
        state.status = status
        state.running = status not in {"stopped", "idle", "error"}
    elif event.type == "RecordingStarted":
        state.running = True
        state.status = "listening"
    elif event.type == "RecordingStopped":
        state.running = False
        state.status = "stopped"
    elif event.type == "AudioLevelChanged":
        state.last_audio_level = float(event.payload.get("level", 0.0))
        state.audio_detected = bool(event.payload.get("speech_detected", False))
        state.in_speech_turn = bool(event.payload.get("in_speech_turn", False))
    elif event.type == "QueueDepthChanged":
        state.queue_depths = {
            "audio_turn_queue": int(event.payload.get("audio_turn_queue", 0)),
            "raw_transcript_queue": int(event.payload.get("raw_transcript_queue", 0)),
        }
    elif event.type == "WorkerOptionsChanged":
        options = event.payload.get("options", {})
        if isinstance(options, dict):
            state.worker_options = {str(key): float(value) for key, value in options.items()}
    elif event.type == "SpeechTurnDiscarded":
        state.discarded_turns.append(
            {
                "turn_id": event.payload.get("turn_id", ""),
                "reason": event.payload.get("reason", ""),
                "duration_seconds": event.payload.get("duration_seconds", 0.0),
                "speech_seconds": event.payload.get("speech_seconds", 0.0),
                "peak_level": event.payload.get("peak_level", 0.0),
                "timestamp": event.timestamp,
            }
        )
    elif event.type == "RawTranscriptReceived":
        state.raw_transcripts.append(
            {
                "turn_id": event.payload.get("turn_id", ""),
                "sequence": event.payload.get("sequence", 0),
                "text": event.payload.get("text", ""),
                "captured_at": event.payload.get("captured_at", 0.0),
                "transcribed_at": event.payload.get("transcribed_at", 0.0),
                "duration_seconds": event.payload.get("duration_seconds", 0.0),
                "speech_seconds": event.payload.get("speech_seconds", 0.0),
                "peak_level": event.payload.get("peak_level", 0.0),
                "timestamp": event.timestamp,
            }
        )
    elif event.type == "TranscriptionDiscarded":
        state.discarded_transcriptions.append(
            {
                "turn_id": event.payload.get("turn_id", ""),
                "text": event.payload.get("text", ""),
                "reason": event.payload.get("reason", ""),
                "timestamp": event.timestamp,
            }
        )
    elif event.type == "SmoothedTranscriptUpdated":
        state.smoothed_text = str(event.payload.get("text", ""))
        if "committed_text" in event.payload:
            state.committed_text = str(event.payload.get("committed_text", ""))
        context_summary = str(event.payload.get("context_summary", "")).strip()
        context_action = str(event.payload.get("context_action", state.context_action))
        if context_summary or context_action == "renew":
            state.context_summary = context_summary
        state.context_action = context_action
    elif event.type == "MergeFeedbackReceived":
        state.feedback.append(
            {
                "turn_id": event.payload.get("turn_id", ""),
                "text": event.payload.get("text", ""),
                "timestamp": event.timestamp,
            }
        )
    elif event.type == "ThoughtCaptured":
        state.thoughts.append(
            {
                "turn_id": event.payload.get("turn_id", ""),
                "text": event.payload.get("text", ""),
                "timestamp": event.timestamp,
            }
        )
    elif event.type == "AssistantError":
        state.errors.append(
            {
                "message": event.payload.get("message", ""),
                "stage": event.payload.get("stage", ""),
                "timestamp": event.timestamp,
            }
        )
        state.status = "error"
        state.running = False
    elif event.type == "PrototypeTranscriptCleared":
        state.raw_transcripts.clear()
        state.discarded_turns.clear()
        state.discarded_transcriptions.clear()
        state.smoothed_text = ""
        state.committed_text = ""
        state.context_summary = ""
        state.context_action = "continue"
        state.feedback.clear()
        state.thoughts.clear()
        state.errors.clear()
        state.last_audio_level = 0.0
        state.audio_detected = False
        state.in_speech_turn = False
        state.queue_depths = {"audio_turn_queue": 0, "raw_transcript_queue": 0}

    return state

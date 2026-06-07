from __future__ import annotations

import queue
import sys
import threading
from dataclasses import dataclass
from typing import Protocol, TextIO

from .events import AssistantEvent


class EventPublisher(Protocol):
    def subscribe(self) -> queue.Queue[AssistantEvent]:
        ...

    def unsubscribe(self, subscriber: queue.Queue[AssistantEvent]) -> None:
        ...


@dataclass
class ConsoleStatus:
    status: str = "stopped"
    stage: str = "idle"
    audio_level: float = 0.0
    audio_detected: bool = False
    in_speech_turn: bool = False
    audio_queue_depth: int = 0
    raw_queue_depth: int = 0


def update_console_status(status: ConsoleStatus, event: AssistantEvent) -> ConsoleStatus:
    payload = event.payload

    if event.type == "AssistantStateChanged":
        status.status = str(payload.get("status", status.status))
    elif event.type == "RecordingStarted":
        status.status = "listening"
        status.stage = "capturing"
    elif event.type == "RecordingStopped":
        status.status = "stopped"
        status.stage = "stopped"
        status.audio_detected = False
        status.in_speech_turn = False
    elif event.type == "AudioLevelChanged":
        status.audio_level = float(payload.get("level", 0.0))
        status.audio_detected = bool(payload.get("speech_detected", False))
        status.in_speech_turn = bool(payload.get("in_speech_turn", False))
    elif event.type == "QueueDepthChanged":
        status.audio_queue_depth = int(payload.get("audio_turn_queue", 0))
        status.raw_queue_depth = int(payload.get("raw_transcript_queue", 0))
    elif event.type == "SpeechTurnDiscarded":
        status.stage = f"discard:{payload.get('reason', '')}"
    elif event.type == "SpeechTurnCompleted":
        status.stage = "queued-stt"
    elif event.type == "TranscriptionStarted":
        status.stage = "transcribing"
    elif event.type == "TranscriptionDiscarded":
        status.stage = f"discard-stt:{payload.get('reason', '')}"
    elif event.type == "RawTranscriptReceived":
        status.stage = "raw-ready"
    elif event.type == "TranscriptMergeStarted":
        status.stage = "merging"
    elif event.type == "TranscriptMergeDeferred":
        status.stage = f"merge-wait:{payload.get('reason', '')}"
    elif event.type == "TranscriptMergeCompleted":
        status.stage = "merged"
    elif event.type == "AssistantError":
        status.status = "error"
        status.stage = f"error:{payload.get('stage', '')}"

    return status


def format_console_status(status: ConsoleStatus) -> str:
    audio = "DETECTED" if status.audio_detected else "quiet"
    turn = "turn" if status.in_speech_turn else "idle"
    return (
        f"status={status.status:<9} "
        f"audio={audio:<8} "
        f"level={status.audio_level:0.3f} "
        f"vad={turn:<4} "
        f"q=audio:{status.audio_queue_depth} text:{status.raw_queue_depth} "
        f"stage={status.stage}"
    )


class ConsoleStatusIndicator:
    def __init__(
        self,
        publisher: EventPublisher,
        stream: TextIO | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.publisher = publisher
        self.stream = stream or sys.stdout
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self.status = ConsoleStatus()
        self._subscriber: queue.Queue[AssistantEvent] | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_length = 0

    def start(self) -> None:
        if not self.enabled:
            return
        self._subscriber = self.publisher.subscribe()
        self._stop_event.clear()
        self._write_status()
        self._thread = threading.Thread(target=self._run, name="pysecretary-console-status", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self._subscriber is not None:
            self.publisher.unsubscribe(self._subscriber)
            self._subscriber = None
        self.stream.write("\n")
        self.stream.flush()

    def _run(self) -> None:
        if self._subscriber is None:
            return
        while not self._stop_event.is_set():
            try:
                event = self._subscriber.get(timeout=0.25)
            except queue.Empty:
                continue
            update_console_status(self.status, event)
            self._write_status()

    def _write_status(self) -> None:
        line = format_console_status(self.status)
        padding = " " * max(0, self._last_length - len(line))
        self.stream.write(f"\r{line}{padding}")
        self.stream.flush()
        self._last_length = len(line)

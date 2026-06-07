from __future__ import annotations

import queue
import re
import threading
import uuid
from dataclasses import dataclass
from time import monotonic as time_monotonic, sleep, time as time_wall
from typing import Callable, Iterator, Protocol

from .audio import AmplitudeVadConfig, AudioTurn, listen_for_speech_turns
from .config import SecretaryConfig
from .context_budget import combine_stable_prefix
from .events import AssistantCommand, AssistantEvent, PrototypeState, make_event, reduce_prototype_state
from .koboldcpp import KoboldCppClient
from .llm import LLMClient
from .stt import (
    SpeechToTextClient,
    clean_transcript_artifacts,
    is_non_content_transcript,
    is_non_speech_transcript,
)
from .transcript import LLMTranscriptMerger, TranscriptMergeResult, TranscriptMerger, TranscriptSection
from .utils import append_text, timestamp


@dataclass(frozen=True)
class QueuedAudioTurn:
    turn_id: str
    sequence: int
    captured_at: float
    turn: AudioTurn


@dataclass(frozen=True)
class QueuedRawTranscript:
    turn_id: str
    sequence: int
    text: str
    captured_at: float
    transcribed_at: float
    duration_seconds: float
    speech_seconds: float
    peak_level: float


class AudioTurnSource(Protocol):
    def turns(self, stop_event: threading.Event) -> Iterator[AudioTurn]:
        ...


@dataclass
class ScriptedTurnSource:
    scripted_turns: list[AudioTurn]

    def turns(self, stop_event: threading.Event) -> Iterator[AudioTurn]:
        for turn in self.scripted_turns:
            if stop_event.is_set():
                break
            yield turn


class MicrophoneTurnSource:
    def __init__(
        self,
        config: SecretaryConfig,
        on_audio_level: Callable[[float, bool, bool], None] | None = None,
        vad_config: AmplitudeVadConfig | None = None,
    ) -> None:
        self.config = config
        self.on_audio_level = on_audio_level
        self.vad_config = vad_config

    def turns(self, stop_event: threading.Event) -> Iterator[AudioTurn]:
        yield from listen_for_speech_turns(
            self.config,
            stop_event,
            on_audio_level=self.on_audio_level,
            vad_config=self.vad_config,
        )


class PrototypeController:
    def __init__(
        self,
        config: SecretaryConfig | None = None,
        turn_source: AudioTurnSource | None = None,
        stt: SpeechToTextClient | None = None,
        merger: TranscriptMerger | None = None,
    ) -> None:
        self.config = config or SecretaryConfig.from_env()
        self._stop_event = threading.Event()
        self._capture_done = threading.Event()
        self._stt_done = threading.Event()
        self._workers: list[threading.Thread] = []
        self._lock = threading.RLock()
        self._subscribers: list[queue.Queue[AssistantEvent]] = []
        self._audio_turn_queue: queue.Queue[QueuedAudioTurn] = queue.Queue()
        self._raw_transcript_queue: queue.Queue[QueuedRawTranscript] = queue.Queue()
        self._stt_active = False
        self._next_sequence = 1
        self._working_sealed = False
        # Shared, mutable VAD/gate thresholds so sensitivity can be re-tuned at runtime
        # (UpdateWorkerOption) while capture keeps reading the same instance.
        self._vad = AmplitudeVadConfig.from_secretary_config(self.config)
        self.state = PrototypeState()

        if stt is None or merger is None:
            kobold = KoboldCppClient.from_config(self.config)
            stt = stt or SpeechToTextClient(self.config, kobold)
            merger = merger or LLMTranscriptMerger(LLMClient(self.config, kobold))

        self.turn_source = turn_source or MicrophoneTurnSource(
            self.config,
            on_audio_level=self._emit_audio_level,
            vad_config=self._vad,
        )
        self.stt = stt
        self.merger = merger
        self._emit_worker_options()

    def handle_command(self, command: AssistantCommand) -> None:
        if command.type == "StartAutomaticCapture":
            self.start()
        elif command.type == "StopAutomaticCapture":
            self.stop()
        elif command.type == "ClearPrototypeTranscript":
            self._emit("PrototypeTranscriptCleared")
        elif command.type == "UpdateWorkerOption":
            self._update_worker_options(command.payload)
        else:
            self._emit("AssistantError", stage="command", message=f"Unknown command: {command.type}")

    def start(self) -> None:
        with self._lock:
            if any(worker.is_alive() for worker in self._workers):
                return
            self._stop_event.clear()
            self._capture_done.clear()
            self._stt_done.clear()
            self._audio_turn_queue = queue.Queue()
            self._raw_transcript_queue = queue.Queue()
            self._next_sequence = 1
            self._working_sealed = False
            self._emit("RecordingStarted")
            self._emit("AssistantStateChanged", status="listening")
            self._emit_queue_depths()
            self._workers = [
                threading.Thread(target=self._capture_loop, name="pysecretary-audio-capture", daemon=True),
                threading.Thread(target=self._stt_loop, name="pysecretary-stt", daemon=True),
                threading.Thread(target=self._merge_loop, name="pysecretary-merge", daemon=True),
            ]
            for worker in self._workers:
                worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._seal_working_to_log(reason="session_stop")
        self._emit("RecordingStopped")
        self._emit("AssistantStateChanged", status="stopped")

    def wait_until_idle(self, timeout: float = 5.0) -> bool:
        workers = list(self._workers)
        if not workers:
            return True
        deadline = time_monotonic() + timeout
        for worker in workers:
            remaining = max(0.0, deadline - time_monotonic())
            worker.join(remaining)
        return not any(worker.is_alive() for worker in workers)

    def subscribe(self) -> queue.Queue[AssistantEvent]:
        subscriber: queue.Queue[AssistantEvent] = queue.Queue()
        with self._lock:
            self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[AssistantEvent]) -> None:
        with self._lock:
            if subscriber in self._subscribers:
                self._subscribers.remove(subscriber)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return self.state.to_dict()

    def _capture_loop(self) -> None:
        try:
            for turn in self.turn_source.turns(self._stop_event):
                if self._stop_event.is_set():
                    break
                self._capture_turn(turn)
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._worker_failed("audio_capture", exc)
        finally:
            self._capture_done.set()
            self._emit_queue_depths()

    def _stt_loop(self) -> None:
        try:
            while True:
                if self._stop_event.is_set() and self._audio_turn_queue.empty():
                    break
                try:
                    queued_turn = self._audio_turn_queue.get(timeout=0.05)
                except queue.Empty:
                    if self._capture_done.is_set():
                        break
                    continue

                try:
                    self._emit_queue_depths()
                    self._process_stt(queued_turn)
                finally:
                    self._audio_turn_queue.task_done()
                    self._emit_queue_depths()
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._worker_failed("stt", exc)
        finally:
            self._stt_done.set()
            self._emit_queue_depths()

    def _merge_loop(self) -> None:
        try:
            while True:
                if self._stop_event.is_set() and self._raw_transcript_queue.empty():
                    break
                try:
                    raw_transcript = self._raw_transcript_queue.get(timeout=self.config.worker_poll_seconds)
                except queue.Empty:
                    if self._stt_done.is_set():
                        break
                    continue

                extra_transcripts: list[QueuedRawTranscript] = []
                try:
                    self._emit_queue_depths()
                    if self._wait_for_merge_slot(raw_transcript.turn_id):
                        extra_transcripts = self._drain_raw_transcript_queue()
                        transcript_batch = [raw_transcript, *extra_transcripts]
                        self._emit_queue_depths()
                        self._process_merge(transcript_batch)
                finally:
                    self._raw_transcript_queue.task_done()
                    for _ in extra_transcripts:
                        self._raw_transcript_queue.task_done()
                    self._emit_queue_depths()
        except Exception as exc:  # pragma: no cover - defensive boundary
            self._worker_failed("merge", exc)
        finally:
            if self._stop_event.is_set():
                self._emit("AssistantStateChanged", status="stopped")
            else:
                self._emit("AssistantStateChanged", status="idle")

    def _capture_turn(self, turn: AudioTurn) -> None:
        turn_id = uuid.uuid4().hex
        sequence = self._allocate_sequence()
        captured_at = time_wall()
        discard_reason = self._turn_discard_reason(turn)
        if discard_reason:
            self._emit(
                "SpeechTurnDiscarded",
                turn_id=turn_id,
                sequence=sequence,
                reason=discard_reason,
                duration_seconds=turn.duration_seconds,
                speech_seconds=turn.speech_seconds,
                peak_level=turn.peak_level,
            )
            return

        self._audio_turn_queue.put(
            QueuedAudioTurn(
                turn_id=turn_id,
                sequence=sequence,
                captured_at=captured_at,
                turn=turn,
            )
        )
        self._emit(
            "SpeechTurnCompleted",
            turn_id=turn_id,
            sequence=sequence,
            duration_seconds=turn.duration_seconds,
            speech_seconds=turn.speech_seconds,
            peak_level=turn.peak_level,
        )
        self._emit_queue_depths()

    def _process_stt(self, queued_turn: QueuedAudioTurn) -> None:
        turn_id = queued_turn.turn_id
        self._set_stt_active(True)
        try:
            self._emit("TranscriptionStarted", turn_id=turn_id)
            raw_text = self.stt.transcribe_audio(queued_turn.turn.wav_bytes).strip()
            if self._stop_event.is_set():
                return
            if not raw_text:
                self._emit("TranscriptionDiscarded", turn_id=turn_id, text="", reason="empty")
                return
            if is_non_speech_transcript(raw_text):
                self._emit("TranscriptionDiscarded", turn_id=turn_id, text=raw_text, reason="non_speech_sentinel")
                return
            # Remove embedded background sound cues (e.g. "(coughing)") before the text
            # reaches the LLM merge worker; discard if nothing meaningful remains.
            content_text = clean_transcript_artifacts(raw_text)
            if not content_text or is_non_content_transcript(content_text):
                self._emit("TranscriptionDiscarded", turn_id=turn_id, text=raw_text, reason="non_content_artifact")
                return
            raw_text = content_text

            transcribed_at = time_wall()
            self._emit(
                "RawTranscriptReceived",
                turn_id=turn_id,
                sequence=queued_turn.sequence,
                text=raw_text,
                captured_at=queued_turn.captured_at,
                transcribed_at=transcribed_at,
                duration_seconds=queued_turn.turn.duration_seconds,
                speech_seconds=queued_turn.turn.speech_seconds,
                peak_level=queued_turn.turn.peak_level,
            )
            self._raw_transcript_queue.put(
                QueuedRawTranscript(
                    turn_id=turn_id,
                    sequence=queued_turn.sequence,
                    text=raw_text,
                    captured_at=queued_turn.captured_at,
                    transcribed_at=transcribed_at,
                    duration_seconds=queued_turn.turn.duration_seconds,
                    speech_seconds=queued_turn.turn.speech_seconds,
                    peak_level=queued_turn.turn.peak_level,
                )
            )
            self._emit_queue_depths()
        finally:
            self._set_stt_active(False)

    def _process_merge(self, raw_transcripts: list[QueuedRawTranscript]) -> None:
        sections = [self._to_transcript_section(raw_transcript) for raw_transcript in raw_transcripts]
        turn_ids = [section.turn_id for section in sections]
        turn_id = turn_ids[-1]
        self._emit(
            "TranscriptMergeStarted",
            turn_id=turn_id,
            turn_ids=turn_ids,
            section_count=len(sections),
        )
        snap = self.snapshot()
        working_in = str(snap.get("smoothed_text", ""))
        committed_in = str(snap.get("committed_text", ""))
        current_context_summary = str(snap.get("context_summary", ""))
        result = self.merger.merge(
            existing_smoothed_text=working_in,
            new_raw_sections=sections,
            recent_raw_context=self._recent_raw_context(),
            current_context_summary=current_context_summary,
        )
        if self._stop_event.is_set():
            return

        # The "smoothed_text" panel stays focused on the current context. When the
        # merge reports a new topic (`renew`), the previous context is sealed into the
        # persistent committed history and the durable full-text log, and the main
        # panel resets to the cleaned new sections. This guarantees prior text is never
        # lost across context switches (full text remains in committed_text + the log).
        if result.context_action == "renew" and working_in.strip():
            committed_out = combine_stable_prefix(committed_in, working_in)
            self._append_full_transcript_log(working_in, reason="context_renew")
        else:
            committed_out = committed_in
        main_text = result.smoothed_text

        for thought in result.thoughts:
            self._emit("ThoughtCaptured", turn_id=turn_id, turn_ids=turn_ids, text=thought)
        for feedback in result.feedback:
            self._emit("MergeFeedbackReceived", turn_id=turn_id, turn_ids=turn_ids, text=feedback)
        self._emit(
            "SmoothedTranscriptUpdated",
            turn_id=turn_id,
            turn_ids=turn_ids,
            section_count=len(sections),
            text=main_text,
            committed_text=committed_out,
            context_summary=result.context_summary,
            context_action=result.context_action,
        )
        self._emit("TranscriptMergeCompleted", turn_id=turn_id, turn_ids=turn_ids, section_count=len(sections))

    def _turn_discard_reason(self, turn: AudioTurn) -> str:
        with self._lock:
            min_speech_seconds = self._vad.min_speech_seconds
            min_peak_level = self._vad.transcription_min_peak_level
        if not turn.wav_bytes:
            return "empty_audio"
        if turn.duration_seconds <= 0:
            return "zero_duration"
        if turn.speech_seconds < min_speech_seconds:
            return "too_short"
        if turn.peak_level < min_peak_level:
            return "low_peak_level"
        return ""

    def _recent_raw_context(self) -> str:
        raw_items = self.snapshot().get("raw_transcripts", [])
        if not isinstance(raw_items, list):
            return ""
        lines = []
        for item in raw_items[-5:]:
            if not isinstance(item, dict):
                continue
            sequence = item.get("sequence", "?")
            lines.append(f"[section {sequence}] {item.get('text', '')}")
        return "\n".join(lines)

    # Runtime-tunable worker options (currently the VAD/turn-gate sensitivity).
    _WORKER_OPTION_FIELDS = (
        "energy_threshold",
        "silence_gap_seconds",
        "min_speech_seconds",
        "max_turn_seconds",
        "transcription_min_peak_level",
    )

    def _update_worker_options(self, payload: dict[str, object]) -> None:
        options = payload.get("options") if isinstance(payload.get("options"), dict) else payload
        if not isinstance(options, dict):
            return
        applied: dict[str, float] = {}
        with self._lock:
            for field in self._WORKER_OPTION_FIELDS:
                if field not in options:
                    continue
                try:
                    value = float(options[field])  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if value < 0:
                    continue
                setattr(self._vad, field, value)
                applied[field] = value
        if applied:
            self._emit_worker_options()

    def _emit_worker_options(self) -> None:
        with self._lock:
            options = {field: float(getattr(self._vad, field)) for field in self._WORKER_OPTION_FIELDS}
        self._emit("WorkerOptionsChanged", options=options)

    def _seal_working_to_log(self, reason: str) -> None:
        with self._lock:
            if self._working_sealed:
                return
            self._working_sealed = True
        working = str(self.snapshot().get("smoothed_text", ""))
        self._append_full_transcript_log(working, reason=reason)

    def _append_full_transcript_log(self, text: str, reason: str) -> None:
        # Best-effort durable record of the full transcript across contexts. Failures
        # here must never disrupt the capture pipeline.
        text = (text or "").strip()
        path = getattr(self.config, "prototype_log_path", "")
        if not text or not path:
            return
        try:
            append_text(path, f"[{timestamp()}] {reason}\n{text}\n{'-' * 60}")
        except OSError:
            if self.config.debug:
                print(f"Could not write prototype transcript log at {path}")

    def _drain_raw_transcript_queue(self) -> list[QueuedRawTranscript]:
        transcripts: list[QueuedRawTranscript] = []
        while True:
            try:
                transcripts.append(self._raw_transcript_queue.get_nowait())
            except queue.Empty:
                return transcripts

    def _to_transcript_section(self, raw_transcript: QueuedRawTranscript) -> TranscriptSection:
        return TranscriptSection(
            turn_id=raw_transcript.turn_id,
            sequence=raw_transcript.sequence,
            text=raw_transcript.text,
            captured_at=raw_transcript.captured_at,
            transcribed_at=raw_transcript.transcribed_at,
            duration_seconds=raw_transcript.duration_seconds,
            speech_seconds=raw_transcript.speech_seconds,
            peak_level=raw_transcript.peak_level,
        )

    def _allocate_sequence(self) -> int:
        with self._lock:
            sequence = self._next_sequence
            self._next_sequence += 1
        return sequence

    def _wait_for_merge_slot(self, turn_id: str) -> bool:
        idle_started: float | None = None
        last_wait_reason = ""
        idle_seconds = max(0.0, self.config.llm_merge_idle_seconds)
        poll_seconds = max(0.01, self.config.worker_poll_seconds)

        while not self._stop_event.is_set():
            wait_reason = self._merge_wait_reason()
            if not wait_reason:
                now = time_monotonic()
                if idle_started is None:
                    idle_started = now
                if now - idle_started >= idle_seconds:
                    return True
            else:
                idle_started = None
                if wait_reason != last_wait_reason:
                    self._emit("TranscriptMergeDeferred", turn_id=turn_id, reason=wait_reason)
                    last_wait_reason = wait_reason
            sleep(poll_seconds)
        return False

    def _merge_wait_reason(self) -> str:
        with self._lock:
            stt_active = self._stt_active

        # Only defer cleanup to keep STT first on the shared local server. We no longer
        # wait for the speaker to stop: with partial-turn streaming, raw sections arrive
        # mid-utterance and are cleaned between STT calls so the transcript updates in near
        # real time. STT still gets priority whenever a turn is being transcribed or audio
        # turns are queued.
        if stt_active:
            return "transcription_active"
        if not self._audio_turn_queue.empty():
            return "audio_turn_backlog"
        return ""

    def _set_stt_active(self, active: bool) -> None:
        with self._lock:
            self._stt_active = active

    def _emit_queue_depths(self) -> None:
        self._emit(
            "QueueDepthChanged",
            audio_turn_queue=self._audio_turn_queue.qsize(),
            raw_transcript_queue=self._raw_transcript_queue.qsize(),
        )

    def _emit_audio_level(
        self,
        level: float,
        speech_detected: bool,
        in_speech_turn: bool,
    ) -> None:
        self._emit(
            "AudioLevelChanged",
            level=level,
            speech_detected=speech_detected,
            in_speech_turn=in_speech_turn,
        )

    def _worker_failed(self, stage: str, exc: Exception) -> None:
        self._stop_event.set()
        self._emit("AssistantError", stage=stage, message=str(exc))

    def _emit(self, event_type: str, **payload: object) -> AssistantEvent:
        event = make_event(event_type, **payload)
        with self._lock:
            reduce_prototype_state(self.state, event)
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(event)
        return event


class DemoSpeechToTextClient:
    def __init__(self) -> None:
        self._responses = [
            "um today we need to test the automatic voice prototype",
            "and uh make sure the raw text and thinking notes show separately",
            "then the smoothed output should keep the important details",
        ]
        self._index = 0

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        return response


class DemoTranscriptMerger:
    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        new_raw_text = " ".join(section.text for section in new_raw_sections)
        cleaned = re.sub(r"\b(um|uh|hmm)\b\s*", "", new_raw_text, flags=re.IGNORECASE).strip()
        if existing_smoothed_text:
            smoothed = f"{existing_smoothed_text}\n{cleaned}"
        else:
            smoothed = cleaned
        return TranscriptMergeResult(
            smoothed_text=smoothed,
            feedback=["Demo merge removed common filler words and appended the new speech section."],
            thoughts=["Demo trace: compared the new raw section against the current smoothed transcript."],
        )


def create_demo_controller(config: SecretaryConfig | None = None) -> PrototypeController:
    turns = [
        AudioTurn(wav_bytes=b"demo-1", duration_seconds=1.2, speech_seconds=0.9, peak_level=0.35),
        AudioTurn(wav_bytes=b"demo-2", duration_seconds=1.0, speech_seconds=0.8, peak_level=0.42),
        AudioTurn(wav_bytes=b"demo-3", duration_seconds=1.1, speech_seconds=0.85, peak_level=0.38),
    ]
    return PrototypeController(
        config=config,
        turn_source=ScriptedTurnSource(turns),
        stt=DemoSpeechToTextClient(),  # type: ignore[arg-type]
        merger=DemoTranscriptMerger(),
    )

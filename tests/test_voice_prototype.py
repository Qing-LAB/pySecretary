import json
import os
import tempfile
import threading
import time
import unittest

from tests.audio_stubs import install_audio_dependency_stubs

install_audio_dependency_stubs()

from pysecretary.audio import AudioTurn
from pysecretary.config import SecretaryConfig
from pysecretary.events import AssistantCommand
from pysecretary.prototype import PrototypeController, ScriptedTurnSource
from pysecretary.transcript import TranscriptMergeResult, TranscriptSection


class FakeStt:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[bytes] = []

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        self.calls.append(audio_bytes)
        return self.responses.pop(0)


class BlockingStt:
    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.first_call_started = threading.Event()
        self.release_first_call = threading.Event()
        self._lock = threading.Lock()

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        with self._lock:
            self.calls.append(audio_bytes)
            call_index = len(self.calls)

        if call_index == 1:
            self.first_call_started.set()
            self.release_first_call.wait(10.0)
        return f"raw text {call_index}"


class BlockingSecondStt:
    def __init__(self) -> None:
        self.calls: list[bytes] = []
        self.second_call_started = threading.Event()
        self.release_second_call = threading.Event()
        self._lock = threading.Lock()

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        with self._lock:
            self.calls.append(audio_bytes)
            call_index = len(self.calls)

        if call_index == 2:
            self.second_call_started.set()
            self.release_second_call.wait(10.0)
        return f"raw text {call_index}"


class FakeMerger:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        new_raw_text = joined_section_text(new_raw_sections)
        self.calls.append(
            {
                "existing": existing_smoothed_text,
                "new_raw": new_raw_text,
                "recent_raw": recent_raw_context,
                "context": current_context_summary,
                "section_count": str(len(new_raw_sections)),
                "sequences": ",".join(str(section.sequence) for section in new_raw_sections),
            }
        )
        return TranscriptMergeResult(
            smoothed_text=new_raw_text.replace("um ", "").strip(),
            feedback=["removed filler"],
            thoughts=["merge debug"],
        )


class BlockingMerger:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.first_call_started = threading.Event()
        self.release_first_call = threading.Event()
        self._lock = threading.Lock()

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        new_raw_text = joined_section_text(new_raw_sections)
        with self._lock:
            self.calls.append(
                {
                    "existing": existing_smoothed_text,
                    "new_raw": new_raw_text,
                    "recent_raw": recent_raw_context,
                    "context": current_context_summary,
                    "section_count": str(len(new_raw_sections)),
                    "sequences": ",".join(str(section.sequence) for section in new_raw_sections),
                }
            )
            call_index = len(self.calls)

        if call_index == 1:
            self.first_call_started.set()
            self.release_first_call.wait(10.0)

        return TranscriptMergeResult(
            smoothed_text=new_raw_text.strip(),
            feedback=[f"merged {call_index}"],
            thoughts=[f"thought {call_index}"],
        )


class RecordingMerger:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        new_raw_text = joined_section_text(new_raw_sections)
        self.calls.append(
            {
                "existing": existing_smoothed_text,
                "new_raw": new_raw_text,
                "recent_raw": recent_raw_context,
                "context": current_context_summary,
                "section_count": str(len(new_raw_sections)),
                "sequences": ",".join(str(section.sequence) for section in new_raw_sections),
            }
        )
        return TranscriptMergeResult(
            smoothed_text=new_raw_text.strip(),
            feedback=[],
            thoughts=[],
        )


class ContextMerger:
    def __init__(self, responses: list[TranscriptMergeResult]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, str]] = []

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        self.calls.append(
            {
                "existing": existing_smoothed_text,
                "new_raw": joined_section_text(new_raw_sections),
                "recent_raw": recent_raw_context,
                "context": current_context_summary,
            }
        )
        return self.responses.pop(0)


class TailMerger:
    """Simulates a model that completes the editable tail with the new words (continue)."""

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        new_raw_text = joined_section_text(new_raw_sections)
        combined = (existing_smoothed_text + " " + new_raw_text).strip()
        return TranscriptMergeResult(smoothed_text=combined, context_action="continue")


class EmptyMerger:
    """Simulates the model returning nothing usable (empty/garbled cleanup)."""

    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        return TranscriptMergeResult(smoothed_text="", feedback=[], thoughts=[])


class RecordingSink:
    def __init__(self) -> None:
        self.delivered: list[str] = []

    def deliver(self, text: str) -> None:
        self.delivered.append(text)


class FailingMerger:
    def merge(
        self,
        existing_smoothed_text: str,
        new_raw_sections: list[TranscriptSection],
        recent_raw_context: str = "",
        current_context_summary: str = "",
    ) -> TranscriptMergeResult:
        raise AssertionError("non-speech transcript should not reach the merger")


def make_turn(name: bytes, peak_level: float = 0.4) -> AudioTurn:
    return AudioTurn(
        wav_bytes=name,
        duration_seconds=1.2,
        speech_seconds=0.9,
        peak_level=peak_level,
    )


def joined_section_text(sections: list[TranscriptSection]) -> str:
    return " ".join(section.text for section in sections)


def wait_for(predicate: object, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():  # type: ignore[operator]
            return True
        time.sleep(0.01)
    return False


class VoicePrototypeTests(unittest.TestCase):
    def test_start_command_processes_scripted_turn_and_updates_state(self) -> None:
        turn = make_turn(b"wav")
        stt = FakeStt(["um prototype text"])
        merger = FakeMerger()
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([turn]),
            stt=stt,  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(stt.calls, [b"wav"])
        self.assertEqual(merger.calls[0]["new_raw"], "um prototype text")
        self.assertEqual(merger.calls[0]["section_count"], "1")
        self.assertEqual(merger.calls[0]["sequences"], "1")
        self.assertEqual(state["raw_transcripts"][0]["text"], "um prototype text")
        self.assertEqual(state["raw_transcripts"][0]["sequence"], 1)
        self.assertEqual(state["smoothed_text"], "prototype text")
        self.assertEqual(state["feedback"][0]["text"], "removed filler")
        self.assertEqual(state["thoughts"][0]["text"], "merge debug")
        self.assertNotIn("merge debug", state["smoothed_text"])

    def test_stop_command_sets_stopped_status(self) -> None:
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([]),
            stt=FakeStt([]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )

        controller.handle_command(AssistantCommand(type="StopAutomaticCapture"))

        state = controller.snapshot()
        self.assertFalse(state["running"])
        self.assertEqual(state["status"], "stopped")

    def test_blank_audio_is_discarded_before_raw_text_and_llm_merge(self) -> None:
        turn = make_turn(b"wav")
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([turn]),
            stt=FakeStt(["BLANK_AUDIO"]),  # type: ignore[arg-type]
            merger=FailingMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(state["raw_transcripts"], [])
        self.assertEqual(state["smoothed_text"], "")
        self.assertEqual(state["discarded_transcriptions"][0]["text"], "BLANK_AUDIO")
        self.assertEqual(state["discarded_transcriptions"][0]["reason"], "non_speech_sentinel")

    def test_audio_caption_artifact_is_discarded_before_raw_text_and_llm_merge(self) -> None:
        turn = make_turn(b"wav")
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([turn]),
            stt=FakeStt(["(upbeat music)"]),  # type: ignore[arg-type]
            merger=FailingMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(state["raw_transcripts"], [])
        self.assertEqual(state["smoothed_text"], "")
        self.assertEqual(state["discarded_transcriptions"][0]["text"], "(upbeat music)")
        self.assertEqual(state["discarded_transcriptions"][0]["reason"], "non_content_artifact")

    def test_no_audio_turn_is_discarded_before_stt(self) -> None:
        turn = AudioTurn(
            wav_bytes=b"",
            duration_seconds=0.0,
            speech_seconds=0.0,
            peak_level=0.0,
        )
        stt = FakeStt(["should not be called"])
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([turn]),
            stt=stt,  # type: ignore[arg-type]
            merger=FailingMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(stt.calls, [])
        self.assertEqual(state["raw_transcripts"], [])
        self.assertEqual(state["discarded_turns"][0]["reason"], "empty_audio")

    def test_low_peak_turn_is_discarded_before_stt(self) -> None:
        turn = AudioTurn(
            wav_bytes=b"wav",
            duration_seconds=1.0,
            speech_seconds=0.8,
            peak_level=0.001,
        )
        stt = FakeStt(["should not be called"])
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([turn]),
            stt=stt,  # type: ignore[arg-type]
            merger=FailingMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(stt.calls, [])
        self.assertEqual(state["discarded_turns"][0]["reason"], "low_peak_level")

    def test_capture_worker_queues_turns_while_stt_is_busy(self) -> None:
        stt = BlockingStt()
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"wav-1"), make_turn(b"wav-2")]),
            stt=stt,  # type: ignore[arg-type]
            merger=FakeMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(stt.first_call_started.wait(2.0))
        self.assertTrue(
            wait_for(
                lambda: sum(1 for event in controller.snapshot()["events"] if event["type"] == "SpeechTurnCompleted") == 2
            )
        )

        state_while_blocked = controller.snapshot()
        self.assertEqual(stt.calls, [b"wav-1"])
        self.assertEqual(state_while_blocked["raw_transcripts"], [])
        self.assertEqual(state_while_blocked["queue_depths"]["audio_turn_queue"], 1)

        stt.release_first_call.set()
        self.assertTrue(controller.wait_until_idle())
        self.assertEqual(stt.calls, [b"wav-1", b"wav-2"])

    def test_stt_worker_batches_accumulated_raw_text_for_merge(self) -> None:
        stt = FakeStt(["raw one", "raw two"])
        merger = RecordingMerger()
        config = SecretaryConfig(llm_merge_idle_seconds=0.05, worker_poll_seconds=0.01)
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"wav-1"), make_turn(b"wav-2")]),
            stt=stt,  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        self.assertEqual(len(merger.calls), 1)
        self.assertEqual(merger.calls[0]["new_raw"], "raw one raw two")
        self.assertEqual(merger.calls[0]["section_count"], "2")
        self.assertEqual(merger.calls[0]["sequences"], "1,2")
        self.assertEqual(controller.snapshot()["smoothed_text"], "raw one raw two")

    def test_merge_waits_while_stt_is_active(self) -> None:
        stt = BlockingSecondStt()
        merger = RecordingMerger()
        config = SecretaryConfig(llm_merge_idle_seconds=0.05, worker_poll_seconds=0.01)
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"wav-1"), make_turn(b"wav-2")]),
            stt=stt,  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(stt.second_call_started.wait(2.0))
        time.sleep(0.1)

        state_while_stt_blocked = controller.snapshot()
        self.assertEqual(merger.calls, [])
        self.assertTrue(
            any(
                event["type"] == "TranscriptMergeDeferred"
                and event["payload"]["reason"] in {"audio_turn_backlog", "transcription_active"}
                for event in state_while_stt_blocked["events"]
            )
        )

        stt.release_second_call.set()
        self.assertTrue(controller.wait_until_idle())
        self.assertEqual([call["new_raw"] for call in merger.calls], ["raw text 1 raw text 2"])
        self.assertEqual(merger.calls[0]["section_count"], "2")
        self.assertEqual(merger.calls[0]["sequences"], "1,2")

    def test_controller_passes_updated_context_summary_to_next_merge(self) -> None:
        stt = FakeStt(["first topic words", "same topic correction"])
        merger = ContextMerger(
            [
                TranscriptMergeResult(
                    smoothed_text="First topic words.",
                    context_summary="first topic context",
                    context_action="continue",
                ),
                TranscriptMergeResult(
                    smoothed_text="First topic words. Same topic correction.",
                    context_summary="updated first topic context",
                    context_action="continue",
                ),
            ]
        )
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"wav")]),
            stt=stt,  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        self.assertEqual(merger.calls[0]["context"], "")
        self.assertEqual(merger.calls[1]["context"], "first topic context")
        self.assertEqual(controller.snapshot()["context_summary"], "updated first topic context")

    def test_transcript_accumulates_across_renew_and_never_shrinks(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        log_path = os.path.join(tmp.name, "full.log")
        config = SecretaryConfig(prototype_log_path=log_path)
        # The merger returns only the cleaned delta; the controller appends it.
        merger = ContextMerger(
            [
                TranscriptMergeResult(smoothed_text="First topic cleaned.", context_summary="first", context_action="continue"),
                TranscriptMergeResult(smoothed_text="Second topic cleaned.", context_summary="second", context_action="renew"),
            ]
        )
        stt = FakeStt(["first topic raw", "second topic raw"])
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=stt,  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        self.assertEqual(controller.snapshot()["smoothed_text"], "First topic cleaned.")

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        full = controller.snapshot()["smoothed_text"]

        # The full transcript grows and keeps both contexts; renew starts a new paragraph.
        self.assertIn("First topic cleaned.", full)
        self.assertIn("Second topic cleaned.", full)
        self.assertIn("\n\n", full)

        with open(log_path, encoding="utf-8") as handle:
            log_text = handle.read()
        self.assertIn("First topic cleaned.", log_text)
        self.assertIn("Second topic cleaned.", log_text)

    def test_continue_merges_new_words_into_editable_tail_and_keeps_head(self) -> None:
        # Small word lookback so a frozen head forms; the editable tail is completed by the
        # new words and spliced back after the head (the seam/split sentence is fixed).
        config = SecretaryConfig(merge_lookback_sentences=0, merge_lookback_words=2)
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["the meeting is", "at noon"]),  # type: ignore[arg-type]
            merger=TailMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        self.assertEqual(controller.snapshot()["smoothed_text"], "the meeting is")

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        # Tail "meeting is" was merged with "at noon"; head "the" preserved → one sentence.
        self.assertEqual(controller.snapshot()["smoothed_text"], "the meeting is at noon")

    def test_paragraph_action_starts_new_paragraph_and_keeps_context(self) -> None:
        merger = ContextMerger(
            [
                TranscriptMergeResult(smoothed_text="First note.", context_action="continue", context_summary="topic"),
                TranscriptMergeResult(smoothed_text="Second note.", context_action="paragraph", context_summary=""),
            ]
        )
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["first", "second"]),  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        state = controller.snapshot()
        self.assertEqual(state["smoothed_text"], "First note.\n\nSecond note.")
        # paragraph keeps the same topic context (only renew would clear/replace it).
        self.assertEqual(state["context_summary"], "topic")

    def test_empty_cleanup_falls_back_to_raw_text(self) -> None:
        # If the model returns nothing usable, the speaker's words must still appear (raw).
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["hello there world"]),  # type: ignore[arg-type]
            merger=EmptyMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        self.assertIn("hello there world", controller.snapshot()["smoothed_text"])

    def test_overlap_is_deduped_across_sections(self) -> None:
        # The second section repeats the first's tail (overlap audio). The duplicate must be
        # trimmed so the transcript does not contain "there there".
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w1"), make_turn(b"w2")]),
            stt=FakeStt(["hello there", "there friend"]),  # type: ignore[arg-type]
            merger=EmptyMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        text = controller.snapshot()["smoothed_text"]
        self.assertIn("hello there friend", text)
        self.assertNotIn("there there", text)

    def test_paragraph_does_not_duplicate_repeated_tail(self) -> None:
        # The model opens a paragraph but re-emits part of the previous text; the repeated
        # lead must be trimmed so the transcript is not duplicated.
        merger = ContextMerger(
            [
                TranscriptMergeResult(smoothed_text="alpha beta gamma delta.", context_action="continue"),
                TranscriptMergeResult(smoothed_text="beta gamma delta epsilon zeta", context_action="paragraph"),
            ]
        )
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["alpha beta gamma delta", "more words here"]),  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        text = str(controller.snapshot()["smoothed_text"])
        self.assertIn("alpha beta gamma delta", text)
        self.assertIn("epsilon zeta", text)
        self.assertEqual(text.count("beta gamma delta"), 1)  # not duplicated

    def test_trace_log_records_raw_stt_and_merge_in_sequence(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        trace_path = os.path.join(tmp.name, "trace.jsonl")
        config = SecretaryConfig(
            prototype_trace_log_path=trace_path,
            prototype_log_path=os.path.join(tmp.name, "snap.log"),
        )
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["hello world here"]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        with open(trace_path, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]
        events = [record["event"] for record in records]
        self.assertIn("session_start", events)
        self.assertIn("stt", events)
        self.assertIn("merge", events)

        stt = next(record for record in records if record["event"] == "stt")
        self.assertEqual(stt["raw"], "hello world here")
        merge = next(record for record in records if record["event"] == "merge")
        self.assertIn("region", merge)
        self.assertIn("tail_in", merge)
        self.assertEqual(merge["sections"], ["hello world here"])

    def test_midsentence_paragraph_is_spliced_not_appended(self) -> None:
        # A partial cut mid-number, then the model returns the corrected continuation but
        # labels it a paragraph. Because the tail ends mid-sentence, it must be spliced in
        # place (no paragraph break, "four" replaced) instead of appended as a duplicate.
        merger = ContextMerger(
            [
                TranscriptMergeResult(smoothed_text="Intro sentence. Moving from the budget of four", context_action="continue"),
                TranscriptMergeResult(smoothed_text="Moving from the budget of forty two.", context_action="paragraph"),
            ]
        )
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["intro", "more"]),  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        text = str(controller.snapshot()["smoothed_text"])
        self.assertIn("forty two", text)
        self.assertNotIn("of four", text)  # the truncated tail was replaced, not duplicated
        self.assertNotIn("\n\n", text)  # no paragraph break inserted mid-sentence

    def test_send_transcript_delivers_only_unsent_text(self) -> None:
        sink = RecordingSink()
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["hello world"]),  # type: ignore[arg-type]
            merger=FakeMerger(),
            sink=sink,  # type: ignore[arg-type]
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        controller.handle_command(AssistantCommand(type="SendTranscript"))
        self.assertEqual(sink.delivered, ["hello world"])

        # Re-sending with no new text delivers nothing.
        controller.handle_command(AssistantCommand(type="SendTranscript"))
        self.assertEqual(sink.delivered, ["hello world"])

        # Only the unsent remainder is delivered after the sent marker moves back.
        controller._sent_text = "hello"
        controller.handle_command(AssistantCommand(type="SendTranscript"))
        self.assertEqual(sink.delivered, ["hello world", "world"])

    def test_send_transcript_without_sink_emits_error(self) -> None:
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["hello world"]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )  # no sink configured
        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        controller.handle_command(AssistantCommand(type="SendTranscript"))

        errors = controller.snapshot()["errors"]
        self.assertTrue(errors and errors[-1]["stage"] == "output")

    def test_clear_resets_sent_marker(self) -> None:
        sink = RecordingSink()
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([]),
            stt=FakeStt([]),  # type: ignore[arg-type]
            merger=FakeMerger(),
            sink=sink,  # type: ignore[arg-type]
        )
        controller._sent_text = "already sent"
        controller.handle_command(AssistantCommand(type="ClearPrototypeTranscript"))
        self.assertEqual(controller._sent_text, "")

    def test_drain_pending_as_raw_preserves_queued_text(self) -> None:
        from pysecretary.llm_queue import LLMRequest
        from pysecretary.prototype import QueuedRawTranscript

        controller = PrototypeController(
            turn_source=ScriptedTurnSource([]),
            stt=FakeStt([]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )
        controller._merge_queue.submit(
            LLMRequest(
                context_key=controller._context_key,
                sequence=1,
                payload=QueuedRawTranscript(
                    turn_id="t",
                    sequence=1,
                    text="unsent words",
                    captured_at=0.0,
                    transcribed_at=0.0,
                    duration_seconds=0.0,
                    speech_seconds=0.0,
                    peak_level=0.0,
                ),
            )
        )

        controller._drain_pending_as_raw()

        self.assertIn("unsent words", controller.snapshot()["smoothed_text"])

    def test_merge_is_not_deferred_by_active_audio_alone(self) -> None:
        # Streaming change: cleanup must run between STT calls during a long utterance,
        # not wait for the speaker to pause. Only STT activity / backlog defers merge.
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([]),
            stt=FakeStt([]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )
        controller.state.audio_detected = True
        controller.state.in_speech_turn = True

        self.assertEqual(controller._merge_wait_reason(), "")

    def test_update_worker_option_command_retunes_sensitivity(self) -> None:
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([]),
            stt=FakeStt([]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )

        controller.handle_command(
            AssistantCommand(
                type="UpdateWorkerOption",
                payload={"options": {"energy_threshold": 0.001, "transcription_min_peak_level": 0.0005}},
            )
        )

        options = controller.snapshot()["worker_options"]
        self.assertEqual(options["energy_threshold"], 0.001)
        self.assertEqual(options["transcription_min_peak_level"], 0.0005)
        # The shared, mutable VAD config the capture loop reads is updated live.
        self.assertEqual(controller._vad.energy_threshold, 0.001)
        self.assertEqual(controller._vad.transcription_min_peak_level, 0.0005)

    def test_background_cue_is_stripped_before_raw_transcript_and_merge(self) -> None:
        merger = RecordingMerger()
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["call Alice (coughing) tomorrow"]),  # type: ignore[arg-type]
            merger=merger,
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(state["raw_transcripts"][0]["text"], "call Alice tomorrow")
        self.assertEqual(merger.calls[0]["new_raw"], "call Alice tomorrow")

    def test_pure_background_cue_turn_is_discarded_before_merge(self) -> None:
        controller = PrototypeController(
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["(coughing)"]),  # type: ignore[arg-type]
            merger=FailingMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())
        state = controller.snapshot()

        self.assertEqual(state["raw_transcripts"], [])
        self.assertEqual(state["discarded_transcriptions"][0]["text"], "(coughing)")
        self.assertEqual(state["discarded_transcriptions"][0]["reason"], "non_content_artifact")

    def test_full_log_receives_cleaned_deltas_in_real_time(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        log_path = os.path.join(tmp.name, "full.log")
        config = SecretaryConfig(prototype_log_path=log_path)
        controller = PrototypeController(
            config=config,
            turn_source=ScriptedTurnSource([make_turn(b"w")]),
            stt=FakeStt(["hello world"]),  # type: ignore[arg-type]
            merger=FakeMerger(),
        )

        controller.handle_command(AssistantCommand(type="StartAutomaticCapture"))
        self.assertTrue(controller.wait_until_idle())

        with open(log_path, encoding="utf-8") as handle:
            log_text = handle.read()
        self.assertIn("hello world", log_text)


if __name__ == "__main__":
    unittest.main()

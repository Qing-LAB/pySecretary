import os
import tempfile
import unittest

from tests.audio_stubs import install_audio_dependency_stubs

install_audio_dependency_stubs()

from pysecretary.app import PySecretary
from pysecretary.config import SecretaryConfig


class FakeStt:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls: list[bytes] = []

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        self.calls.append(audio_bytes)
        return self.response


class FakeLlm:
    """Records calls and returns scripted text per stage."""

    def __init__(
        self,
        cleaned: str = "",
        task: str = "",
        summary: str = "",
    ) -> None:
        self.cleaned = cleaned
        self.task = task
        self.summary = summary
        self.clean_calls: list[str] = []
        self.detect_calls: list[str] = []
        self.summarize_calls: list[tuple[str, str]] = []

    def clean_and_organize(self, raw_text: str) -> str:
        self.clean_calls.append(raw_text)
        return self.cleaned

    def detect_task_request(self, cleaned_text: str) -> str:
        self.detect_calls.append(cleaned_text)
        return self.task

    def summarize_task_result(self, task_description: str, task_result: str) -> str:
        self.summarize_calls.append((task_description, task_result))
        return self.summary


class FakeTts:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


class AppThoughtSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.transcript_path = os.path.join(self._tmp.name, "conversation.txt")
        self.thought_path = os.path.join(self._tmp.name, "thoughts.log")

    def _make(self, llm: FakeLlm, stt: FakeStt | None = None) -> tuple[PySecretary, FakeTts]:
        config = SecretaryConfig(
            transcript_path=self.transcript_path,
            thought_log_path=self.thought_path,
        )
        tts = FakeTts()
        secretary = PySecretary(
            config=config,
            stt=stt or FakeStt(),  # type: ignore[arg-type]
            llm=llm,  # type: ignore[arg-type]
            tts=tts,  # type: ignore[arg-type]
        )
        return secretary, tts

    def _read(self, path: str) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def test_construction_with_injected_clients_makes_no_network_call(self) -> None:
        # If construction tried to build a real KoboldCppClient it would attempt
        # discovery over HTTP; injecting all three clients must avoid that.
        secretary, _tts = self._make(FakeLlm(cleaned="hi"))
        self.assertIsInstance(secretary, PySecretary)

    def test_think_block_is_stripped_before_tts_and_logged_separately(self) -> None:
        llm = FakeLlm(cleaned="<think>secret plan</think>Hello world.")
        secretary, tts = self._make(llm)

        secretary._handle_transcript("hello there")

        self.assertEqual(tts.spoken, ["Hello world."])
        # Thought content must never reach the spoken path or the transcript file.
        self.assertNotIn("secret plan", "".join(tts.spoken))
        transcript = self._read(self.transcript_path)
        self.assertIn("Hello world.", transcript)
        self.assertNotIn("secret plan", transcript)
        self.assertNotIn("<think>", transcript)
        # Thought trace is persisted in the separate thought log.
        self.assertIn("secret plan", self._read(self.thought_path))

    def test_thought_only_output_blocks_speech(self) -> None:
        llm = FakeLlm(cleaned="<think>only internal reasoning, nothing to say</think>")
        secretary, tts = self._make(llm)

        secretary._handle_transcript("mumble")

        self.assertEqual(tts.spoken, [])
        self.assertIn("only internal reasoning", self._read(self.thought_path))
        transcript = self._read(self.transcript_path)
        self.assertNotIn("only internal reasoning", transcript)

    def test_non_speech_sentinel_is_dropped_before_llm_and_tts(self) -> None:
        llm = FakeLlm(cleaned="should not be produced")
        secretary, tts = self._make(llm)

        secretary._handle_transcript("BLANK_AUDIO")

        self.assertEqual(llm.clean_calls, [])
        self.assertEqual(tts.spoken, [])
        self.assertEqual(self._read(self.transcript_path), "")

    def test_audio_caption_artifact_is_dropped_before_llm_and_tts(self) -> None:
        llm = FakeLlm(cleaned="should not be produced")
        secretary, tts = self._make(llm)

        secretary._handle_transcript("(upbeat music)")

        self.assertEqual(llm.clean_calls, [])
        self.assertEqual(tts.spoken, [])

    def test_manual_command_skips_non_speech_gate(self) -> None:
        # Manual text is trusted; even sentinel-looking text is processed.
        llm = FakeLlm(cleaned="Reminder noted.")
        secretary, tts = self._make(llm)

        secretary._handle_text_command("blank")

        self.assertEqual(llm.clean_calls, ["blank"])
        self.assertEqual(tts.spoken, ["Reminder noted."])

    def test_task_path_speaks_sanitized_summary_and_logs_thoughts(self) -> None:
        llm = FakeLlm(
            cleaned="Please email John about the report.",
            task="send email to John",
            summary="<think>drafting the note</think>I emailed John about the report.",
        )
        secretary, tts = self._make(llm)

        secretary._handle_transcript("email john about the report")

        self.assertEqual(tts.spoken, ["I emailed John about the report."])
        self.assertEqual(llm.summarize_calls[0][0], "send email to John")
        thoughts = self._read(self.thought_path)
        self.assertIn("Detected task: send email to John", thoughts)
        self.assertIn("drafting the note", thoughts)
        self.assertNotIn("drafting the note", self._read(self.transcript_path))

    def test_empty_transcription_is_ignored(self) -> None:
        llm = FakeLlm(cleaned="unused")
        secretary, tts = self._make(llm)

        secretary._handle_transcript("   ")

        self.assertEqual(llm.clean_calls, [])
        self.assertEqual(tts.spoken, [])


if __name__ == "__main__":
    unittest.main()

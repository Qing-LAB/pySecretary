import threading

from .audio import record_audio_segment
from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient
from .llm import LLMClient
from .stt import (
    SpeechToTextClient,
    clean_transcript_artifacts,
    is_non_content_transcript,
    is_non_speech_transcript,
)
from .transcript import split_thought_text
from .tts import TextToSpeechClient
from .utils import append_text, print_section, timestamp


class PySecretary:
    """Simple synchronous voice loop.

    This is the dependency-light "simple mode" orchestrator. It records one
    fixed-length segment, transcribes it, cleans it, optionally routes a task,
    and speaks a thought-safe result before listening again. The event-driven,
    continuous-capture pipeline lives in ``pysecretary.prototype``; see
    ``docs/modules/app.md`` for how the two relate.

    Design contract enforced here:

    - ``<think>...</think>`` reasoning is split out before any text reaches TTS
      (``docs/DESIGN.md`` Design Rules) and stored separately in the thought log.
    - STT non-speech sentinels and audio-caption artifacts never reach the LLM
      or TTS (``docs/modules/voice_prototype.md`` Non-Speech STT Filtering).
    """

    def __init__(
        self,
        config: SecretaryConfig | None = None,
        stt: SpeechToTextClient | None = None,
        llm: LLMClient | None = None,
        tts: TextToSpeechClient | None = None,
    ) -> None:
        self.config = config or SecretaryConfig.from_env()
        if stt is None or llm is None or tts is None:
            kobold = KoboldCppClient.from_config(self.config)
            stt = stt or SpeechToTextClient(self.config, kobold)
            llm = llm or LLMClient(self.config, kobold)
            tts = tts or TextToSpeechClient(self.config, kobold)
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.stop_event = threading.Event()
        self.history_path = self.config.transcript_path
        self.thought_path = self.config.thought_log_path

    def start(self) -> None:
        print("pySecretary starting. Press Ctrl+C to stop.")
        print("Type 'exit' or 'quit' in the console to stop cleanly.")

        input_thread = threading.Thread(target=self._console_loop, daemon=True)
        input_thread.start()

        try:
            while not self.stop_event.is_set():
                self._process_audio_cycle()
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self.stop_event.set()
        print("Stopping pySecretary...")

    def _console_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                command = input().strip()
            except EOFError:
                break
            if not command:
                continue
            if command.lower() in {"exit", "quit", "stop"}:
                self.stop()
                break
            self._handle_text_command(command)

    def _handle_text_command(self, text: str) -> None:
        # Manual text is trusted user input, so it skips the STT non-speech gate.
        print_section("Manual command received", text)
        self._process_text(text)

    def _process_audio_cycle(self) -> None:
        audio_bytes = record_audio_segment(self.config)
        raw_text = self.stt.transcribe_audio(audio_bytes)
        self._handle_transcript(raw_text)

    def _handle_transcript(self, raw_text: str) -> None:
        raw_text = (raw_text or "").strip()
        if not raw_text or is_non_speech_transcript(raw_text):
            if self.config.debug:
                print(f"Discarded non-speech transcription: {raw_text!r}")
            return

        # Strip embedded background sound cues (e.g. "(coughing)") before the LLM.
        content_text = clean_transcript_artifacts(raw_text)
        if not content_text or is_non_content_transcript(content_text):
            if self.config.debug:
                print(f"Discarded non-content transcription: {raw_text!r}")
            return

        print_section("Raw transcript", raw_text)
        self._process_text(content_text)

    def _process_text(self, raw_text: str) -> None:
        cleaned_split = split_thought_text(self.llm.clean_and_organize(raw_text))
        cleaned_text = cleaned_split.final_text
        print_section("Cleaned text", cleaned_text)

        spoken_text, task_thoughts = self._apply_task_logic(cleaned_text)
        thoughts = cleaned_split.thoughts + task_thoughts
        self._speak_and_save(raw_text, cleaned_text, spoken_text, thoughts)

    def _apply_task_logic(self, cleaned_text: str) -> tuple[str, list[str]]:
        task_description = self.llm.detect_task_request(cleaned_text)
        if not task_description:
            if self.config.debug:
                print("No follow-up task detected.")
            return cleaned_text, []

        thoughts = [f"Detected task: {task_description}"]
        print_section("Task detected", thoughts[0])

        task_result = self.external_api_call(task_description)
        summary_split = split_thought_text(
            self.llm.summarize_task_result(task_description, task_result)
        )
        thoughts.extend(summary_split.thoughts)
        return summary_split.final_text, thoughts

    def external_api_call(self, task: str) -> str:
        return (
            "This assistant detected a follow-up request but has not yet been configured to call an external API. "
            "Extend the `external_api_call` method in `pysecretary/app.py` to connect to a search engine, knowledge service, calendar API, or other external tool. "
            f"Task: {task}"
        )

    def _speak_and_save(
        self,
        raw_text: str,
        cleaned_text: str,
        spoken_text: str,
        thoughts: list[str],
    ) -> None:
        spoken_text = (spoken_text or "").strip()
        self._save_history(raw_text, cleaned_text, spoken_text)
        if thoughts:
            self._save_thoughts(raw_text, thoughts)
            print_section("Thoughts (not spoken)", "\n".join(thoughts))

        if not spoken_text:
            # Only thought/empty content remained; block speech rather than leak it.
            print_section("Spoken output", "[blocked: no safe final text to speak]")
            return

        print_section("Spoken output", spoken_text)
        self.tts.speak(spoken_text)

    def _save_history(self, raw_text: str, cleaned_text: str, spoken_text: str) -> None:
        entry = (
            f"[{timestamp()}]\n"
            "RAW TRANSCRIPT:\n"
            f"{raw_text}\n\n"
            "CLEANED TEXT:\n"
            f"{cleaned_text}\n\n"
            "SPOKEN OUTPUT:\n"
            f"{spoken_text}\n"
            "-" * 60
        )
        append_text(self.history_path, entry)

    def _save_thoughts(self, raw_text: str, thoughts: list[str]) -> None:
        # Thought traces are persisted to a separate file so they never mix with
        # the spoken/conversation transcript (docs/modules/app.md Thought Safety).
        entry = (
            f"[{timestamp()}]\n"
            "SOURCE TRANSCRIPT:\n"
            f"{raw_text}\n\n"
            "THOUGHT TRACES:\n"
            + "\n".join(f"- {thought}" for thought in thoughts)
            + "\n"
            + "-" * 60
        )
        append_text(self.thought_path, entry)


def main() -> None:
    secretary = PySecretary()
    secretary.start()

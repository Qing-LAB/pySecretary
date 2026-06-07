import threading

from .audio import record_audio_segment
from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient
from .llm import LLMClient
from .stt import SpeechToTextClient
from .tts import TextToSpeechClient
from .utils import append_text, print_section, timestamp


class PySecretary:
    def __init__(self, config: SecretaryConfig | None = None) -> None:
        self.config = config or SecretaryConfig.from_env()
        self.kobold = KoboldCppClient.from_config(self.config)
        self.stt = SpeechToTextClient(self.config, self.kobold)
        self.llm = LLMClient(self.config, self.kobold)
        self.tts = TextToSpeechClient(self.config, self.kobold)
        self.stop_event = threading.Event()
        self.history_path = self.config.transcript_path

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
        print_section("Manual command received", text)
        cleaned = self.llm.clean_and_organize(text)
        result = self._apply_task_logic(cleaned)
        self._speak_and_save(text, cleaned, result)

    def _process_audio_cycle(self) -> None:
        audio_bytes = record_audio_segment(self.config)
        raw_text = self.stt.transcribe_audio(audio_bytes)
        if not raw_text:
            if self.config.debug:
                print("No speech detected in the latest segment.")
            return

        print_section("Raw transcript", raw_text)
        cleaned_text = self.llm.clean_and_organize(raw_text)
        print_section("Cleaned text", cleaned_text)

        final_result = self._apply_task_logic(cleaned_text)
        self._speak_and_save(raw_text, cleaned_text, final_result)

    def _apply_task_logic(self, cleaned_text: str) -> str:
        task_description = self.llm.detect_task_request(cleaned_text)
        if not task_description:
            if self.config.debug:
                print("No follow-up task detected.")
            return cleaned_text

        thought = f"Detected task: {task_description}"
        print_section("Task detected", thought)

        task_result = self.external_api_call(task_description)
        spoken_result = self.llm.summarize_task_result(task_description, task_result)
        return spoken_result

    def external_api_call(self, task: str) -> str:
        return (
            "This assistant detected a follow-up request but has not yet been configured to call an external API. "
            "Extend the `external_api_call` method in `pysecretary/app.py` to connect to a search engine, knowledge service, calendar API, or other external tool. "
            f"Task: {task}"
        )

    def _speak_and_save(self, raw_text: str, cleaned_text: str, output_text: str) -> None:
        self._save_history(raw_text, cleaned_text, output_text)
        print_section("Spoken output", output_text)
        self.tts.speak(output_text)

    def _save_history(self, raw_text: str, cleaned_text: str, output_text: str) -> None:
        entry = (
            f"[{timestamp()}]\n"
            "RAW TRANSCRIPT:\n"
            f"{raw_text}\n\n"
            "CLEANED TEXT:\n"
            f"{cleaned_text}\n\n"
            "FINAL OUTPUT:\n"
            f"{output_text}\n"
            "-" * 60
        )
        append_text(self.history_path, entry)


def main() -> None:
    secretary = PySecretary()
    secretary.start()

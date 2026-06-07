import unittest

from pysecretary.console import ConsoleStatus, format_console_status, update_console_status
from pysecretary.events import make_event


class ConsoleStatusTests(unittest.TestCase):
    def test_audio_level_event_updates_single_line_status_fields(self) -> None:
        status = ConsoleStatus()

        update_console_status(
            status,
            make_event("AudioLevelChanged", level=0.037, speech_detected=True, in_speech_turn=True),
        )
        update_console_status(
            status,
            make_event("QueueDepthChanged", audio_turn_queue=2, raw_transcript_queue=1),
        )

        line = format_console_status(status)

        self.assertIn("audio=DETECTED", line)
        self.assertIn("level=0.037", line)
        self.assertIn("vad=turn", line)
        self.assertIn("q=audio:2 text:1", line)

    def test_recording_stop_clears_audio_detection(self) -> None:
        status = ConsoleStatus(audio_detected=True, in_speech_turn=True, audio_level=0.5)

        update_console_status(status, make_event("RecordingStopped"))

        line = format_console_status(status)
        self.assertIn("status=stopped", line)
        self.assertIn("audio=quiet", line)
        self.assertIn("vad=idle", line)


if __name__ == "__main__":
    unittest.main()

import io
import unittest

from pysecretary.output_bridge import (
    ClipboardSink,
    KeystrokeSink,
    StdoutSink,
    TranscriptSink,
    make_sink,
)


class OutputBridgeTests(unittest.TestCase):
    def test_stdout_sink_writes_one_line_per_utterance(self) -> None:
        buffer = io.StringIO()
        sink = StdoutSink(stream=buffer)

        sink.deliver("first utterance")
        sink.deliver("second utterance")

        self.assertEqual(buffer.getvalue(), "first utterance\nsecond utterance\n")
        self.assertIsInstance(sink, TranscriptSink)

    def test_make_sink_resolves_names(self) -> None:
        self.assertIsNone(make_sink(""))
        self.assertIsNone(make_sink("none"))
        self.assertIsInstance(make_sink("stdout"), StdoutSink)
        self.assertIsInstance(make_sink("clipboard"), ClipboardSink)
        self.assertIsInstance(make_sink("keystroke"), KeystrokeSink)

    def test_make_sink_rejects_unknown(self) -> None:
        with self.assertRaises(ValueError):
            make_sink("telepathy")

    def test_clipboard_sink_auto_paste_flag(self) -> None:
        self.assertFalse(ClipboardSink().auto_paste)
        self.assertTrue(ClipboardSink(auto_paste=True).auto_paste)


if __name__ == "__main__":
    unittest.main()

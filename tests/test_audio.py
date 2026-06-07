import importlib
import unittest

from pysecretary.config import SecretaryConfig
from tests.audio_stubs import FakeAudioData, install_audio_dependency_stubs


class AudioTests(unittest.TestCase):
    def test_record_audio_segment_writes_wav_bytes(self) -> None:
        state = install_audio_dependency_stubs()
        audio = importlib.import_module("pysecretary.audio")
        config = SecretaryConfig(sample_rate=8000, segment_seconds=3)

        result = audio.record_audio_segment(config)

        self.assertEqual(result, b"fake-wav")
        self.assertEqual(
            state.rec_calls[0],
            {
                "samples": 24000,
                "samplerate": 8000,
                "channels": 1,
                "dtype": "int16",
            },
        )
        self.assertEqual(state.write_calls[0]["format"], "WAV")
        self.assertEqual(state.write_calls[0]["subtype"], "PCM_16")
        self.assertEqual(state.wait_count, 1)

    def test_play_audio_bytes_reads_and_plays_wav(self) -> None:
        state = install_audio_dependency_stubs()
        audio = importlib.import_module("pysecretary.audio")

        audio.play_audio_bytes(b"wav-data", SecretaryConfig())

        self.assertEqual(state.read_calls[0]["dtype"], "int16")
        self.assertEqual(state.read_calls[0]["bytes"], b"wav-data")
        self.assertEqual(state.play_calls[0]["data"], state.playback_data)
        self.assertEqual(state.play_calls[0]["samplerate"], state.playback_samplerate)
        self.assertEqual(state.wait_count, 1)

    def test_play_audio_bytes_skips_empty_audio(self) -> None:
        state = install_audio_dependency_stubs()
        state.playback_data = FakeAudioData(size=0)
        audio = importlib.import_module("pysecretary.audio")

        audio.play_audio_bytes(b"wav-data", SecretaryConfig())

        self.assertEqual(state.play_calls, [])
        self.assertEqual(state.wait_count, 0)


if __name__ == "__main__":
    unittest.main()


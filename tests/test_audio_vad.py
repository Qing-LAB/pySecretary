import importlib
import unittest

from tests.audio_stubs import install_audio_dependency_stubs


class AudioVadTests(unittest.TestCase):
    def setUp(self) -> None:
        install_audio_dependency_stubs()
        self.audio = importlib.import_module("pysecretary.audio")

    def test_detector_emits_turn_after_significant_gap(self) -> None:
        config = self.audio.AmplitudeVadConfig(
            sample_rate=4,
            chunk_seconds=0.25,
            energy_threshold=0.1,
            silence_gap_seconds=0.5,
            min_speech_seconds=0.5,
            max_turn_seconds=5,
        )
        detector = self.audio.AudioTurnDetector(config)

        self.assertIsNone(detector.accept_chunk([4000]))
        self.assertIsNone(detector.accept_chunk([4000]))
        self.assertIsNone(detector.accept_chunk([0]))
        turn = detector.accept_chunk([0])

        self.assertIsNotNone(turn)
        self.assertGreater(turn.duration_seconds, 0)
        self.assertEqual(turn.speech_seconds, 0.5)
        self.assertGreater(turn.peak_level, 0.1)
        self.assertTrue(turn.wav_bytes.startswith(b"RIFF"))

    def test_detector_tracks_latest_speech_state_for_status_feedback(self) -> None:
        config = self.audio.AmplitudeVadConfig(
            sample_rate=4,
            chunk_seconds=0.25,
            energy_threshold=0.1,
            silence_gap_seconds=0.5,
            min_speech_seconds=0.5,
            max_turn_seconds=5,
        )
        detector = self.audio.AudioTurnDetector(config)

        detector.accept_chunk([0])
        self.assertFalse(detector.last_is_speech)
        self.assertFalse(detector.in_speech_turn)

        detector.accept_chunk([4000])
        self.assertTrue(detector.last_is_speech)
        self.assertTrue(detector.in_speech_turn)

    def test_detector_drops_tiny_noise_turn(self) -> None:
        config = self.audio.AmplitudeVadConfig(
            sample_rate=4,
            chunk_seconds=0.25,
            energy_threshold=0.1,
            silence_gap_seconds=0.25,
            min_speech_seconds=0.5,
            max_turn_seconds=5,
        )
        detector = self.audio.AudioTurnDetector(config)

        self.assertIsNone(detector.accept_chunk([4000]))
        self.assertIsNone(detector.accept_chunk([0]))

    def test_detector_flushes_partial_during_long_speech_and_keeps_listening(self) -> None:
        config = self.audio.AmplitudeVadConfig(
            sample_rate=4,
            chunk_seconds=0.25,
            energy_threshold=0.1,
            silence_gap_seconds=10,
            min_speech_seconds=0.25,
            max_turn_seconds=100,
            partial_turn_seconds=0.5,
            partial_overlap_seconds=0.25,
        )
        detector = self.audio.AudioTurnDetector(config)

        self.assertIsNone(detector.accept_chunk([4000]))
        partial = detector.accept_chunk([4000])

        self.assertIsNotNone(partial)
        self.assertTrue(partial.is_partial)
        # The utterance is still in progress after a partial flush.
        self.assertTrue(detector.in_speech_turn)

        final = detector.finish()
        self.assertIsNotNone(final)
        self.assertFalse(final.is_partial)

    def test_detector_forces_turn_at_max_duration(self) -> None:
        config = self.audio.AmplitudeVadConfig(
            sample_rate=4,
            chunk_seconds=0.25,
            energy_threshold=0.1,
            silence_gap_seconds=10,
            min_speech_seconds=0.25,
            max_turn_seconds=0.5,
        )
        detector = self.audio.AudioTurnDetector(config)

        self.assertIsNone(detector.accept_chunk([4000]))
        turn = detector.accept_chunk([4000])

        self.assertIsNotNone(turn)
        self.assertEqual(turn.speech_seconds, 0.5)


if __name__ == "__main__":
    unittest.main()

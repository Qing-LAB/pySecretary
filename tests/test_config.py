import os
import unittest
from unittest.mock import patch

from pysecretary.config import SecretaryConfig


class SecretaryConfigTests(unittest.TestCase):
    def test_from_env_uses_project_defaults(self) -> None:
        with patch("pysecretary.config.load_dotenv", return_value=False):
            with patch.dict(os.environ, {}, clear=True):
                config = SecretaryConfig.from_env()

        self.assertEqual(config.api_base, "http://localhost:5001")
        self.assertIsNone(config.api_key)
        self.assertEqual(config.stt_model, "kcpp")
        self.assertEqual(config.llm_model, "kcpp")
        self.assertEqual(config.tts_model, "kcpp")
        self.assertEqual(config.voice, "alloy")
        self.assertEqual(config.sample_rate, 16000)
        self.assertEqual(config.segment_seconds, 7)
        self.assertEqual(config.audio_chunk_seconds, 0.25)
        self.assertEqual(config.vad_energy_threshold, 0.006)
        self.assertEqual(config.silence_gap_seconds, 1.0)
        self.assertEqual(config.min_speech_seconds, 0.25)
        self.assertEqual(config.max_turn_seconds, 20.0)
        self.assertEqual(config.transcription_min_peak_level, 0.004)
        # The keep-gate must not exceed the start threshold, or detected speech is dropped.
        self.assertLessEqual(config.transcription_min_peak_level, config.vad_energy_threshold)
        self.assertEqual(config.partial_turn_seconds, 6.0)
        self.assertEqual(config.partial_overlap_seconds, 1.0)
        self.assertTrue(config.llm_disable_thinking)
        self.assertEqual(config.llm_context_window_tokens, 16384)
        self.assertEqual(config.llm_context_response_reserved_tokens, 1024)
        self.assertEqual(config.llm_context_prompt_overhead_tokens, 768)
        self.assertEqual(config.llm_context_safety_tokens, 256)
        self.assertEqual(config.transcript_path, "conversation.txt")
        self.assertEqual(config.thought_log_path, "thoughts.log")
        self.assertEqual(config.prototype_log_path, "prototype_transcript.log")
        self.assertEqual(config.prototype_host, "127.0.0.1")
        self.assertEqual(config.prototype_port, 8765)
        self.assertEqual(config.request_timeout, 120.0)
        self.assertEqual(config.discovery_timeout, 5.0)
        self.assertFalse(config.debug)

    def test_from_env_parses_overrides(self) -> None:
        env = {
            "PSEC_API_BASE": "http://example.test:5001",
            "PSEC_API_KEY": "secret",
            "PSEC_STT_MODEL": "stt-model",
            "PSEC_LLM_MODEL": "llm-model",
            "PSEC_TTS_MODEL": "tts-model",
            "PSEC_TTS_VOICE": "voice",
            "PSEC_SAMPLE_RATE": "24000",
            "PSEC_SEGMENT_SECONDS": "4",
            "PSEC_AUDIO_CHUNK_SECONDS": "0.1",
            "PSEC_VAD_ENERGY_THRESHOLD": "0.03",
            "PSEC_SILENCE_GAP_SECONDS": "0.8",
            "PSEC_MIN_SPEECH_SECONDS": "0.2",
            "PSEC_MAX_TURN_SECONDS": "12.5",
            "PSEC_PARTIAL_TURN_SECONDS": "4.5",
            "PSEC_PARTIAL_OVERLAP_SECONDS": "0.75",
            "PSEC_LLM_DISABLE_THINKING": "0",
            "PSEC_TRANSCRIPTION_MIN_PEAK_LEVEL": "0.04",
            "PSEC_LLM_CONTEXT_WINDOW_TOKENS": "12288",
            "PSEC_LLM_CONTEXT_RESPONSE_RESERVED_TOKENS": "512",
            "PSEC_LLM_CONTEXT_PROMPT_OVERHEAD_TOKENS": "333",
            "PSEC_LLM_CONTEXT_SAFETY_TOKENS": "111",
            "PSEC_OUTPUT_WAV_PATH": "/tmp/out.wav",
            "PSEC_TRANSCRIPT_PATH": "/tmp/transcript.txt",
            "PSEC_THOUGHT_LOG_PATH": "/tmp/thoughts.log",
            "PSEC_PROTOTYPE_LOG_PATH": "/tmp/prototype_transcript.log",
            "PSEC_PROTOTYPE_HOST": "0.0.0.0",
            "PSEC_PROTOTYPE_PORT": "9001",
            "PSEC_REQUEST_TIMEOUT": "33.5",
            "PSEC_DISCOVERY_TIMEOUT": "2.5",
            "PSEC_DEBUG": "yes",
        }

        with patch("pysecretary.config.load_dotenv", return_value=True):
            with patch.dict(os.environ, env, clear=True):
                config = SecretaryConfig.from_env()

        self.assertEqual(config.api_base, "http://example.test:5001")
        self.assertEqual(config.api_key, "secret")
        self.assertEqual(config.stt_model, "stt-model")
        self.assertEqual(config.llm_model, "llm-model")
        self.assertEqual(config.tts_model, "tts-model")
        self.assertEqual(config.voice, "voice")
        self.assertEqual(config.sample_rate, 24000)
        self.assertEqual(config.segment_seconds, 4)
        self.assertEqual(config.audio_chunk_seconds, 0.1)
        self.assertEqual(config.vad_energy_threshold, 0.03)
        self.assertEqual(config.silence_gap_seconds, 0.8)
        self.assertEqual(config.min_speech_seconds, 0.2)
        self.assertEqual(config.max_turn_seconds, 12.5)
        self.assertEqual(config.partial_turn_seconds, 4.5)
        self.assertEqual(config.partial_overlap_seconds, 0.75)
        self.assertFalse(config.llm_disable_thinking)
        self.assertEqual(config.transcription_min_peak_level, 0.04)
        self.assertEqual(config.llm_context_window_tokens, 12288)
        self.assertEqual(config.llm_context_response_reserved_tokens, 512)
        self.assertEqual(config.llm_context_prompt_overhead_tokens, 333)
        self.assertEqual(config.llm_context_safety_tokens, 111)
        self.assertEqual(config.output_wav_path, "/tmp/out.wav")
        self.assertEqual(config.transcript_path, "/tmp/transcript.txt")
        self.assertEqual(config.thought_log_path, "/tmp/thoughts.log")
        self.assertEqual(config.prototype_log_path, "/tmp/prototype_transcript.log")
        self.assertEqual(config.prototype_host, "0.0.0.0")
        self.assertEqual(config.prototype_port, 9001)
        self.assertEqual(config.request_timeout, 33.5)
        self.assertEqual(config.discovery_timeout, 2.5)
        self.assertTrue(config.debug)

    def test_empty_api_key_becomes_none(self) -> None:
        with patch("pysecretary.config.load_dotenv", return_value=False):
            with patch.dict(os.environ, {"PSEC_API_KEY": ""}, clear=True):
                config = SecretaryConfig.from_env()

        self.assertIsNone(config.api_key)


if __name__ == "__main__":
    unittest.main()

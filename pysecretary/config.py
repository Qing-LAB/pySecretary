import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


@dataclass
class SecretaryConfig:
    api_base: str = "http://localhost:5001"
    api_key: str | None = None
    stt_model: str = "kcpp"
    llm_model: str = "kcpp"
    tts_model: str = "kcpp"
    voice: str = "alloy"
    sample_rate: int = 16000
    segment_seconds: int = 7
    audio_chunk_seconds: float = 0.25
    vad_energy_threshold: float = 0.006
    silence_gap_seconds: float = 1.0
    min_speech_seconds: float = 0.25
    max_turn_seconds: float = 20.0
    partial_turn_seconds: float = 10.0
    partial_overlap_seconds: float = 1.0
    partial_overlap_min_gap_seconds: float = 0.3
    partial_overlap_max_seconds: float = 2.0
    transcription_min_peak_level: float = 0.004
    llm_merge_idle_seconds: float = 0.75
    llm_merge_max_tokens: int = 1024
    llm_merge_max_sections: int = 4
    llm_disable_thinking: bool = True
    merge_lookback_sentences: int = 1
    merge_lookback_words: int = 40
    worker_poll_seconds: float = 0.05
    output_wav_path: str = "output.wav"
    transcript_path: str = "conversation.txt"
    thought_log_path: str = "thoughts.log"
    prototype_log_path: str = "prototype_transcript.log"
    prototype_host: str = "127.0.0.1"
    prototype_port: int = 8765
    request_timeout: float = 120.0
    discovery_timeout: float = 5.0
    debug: bool = False

    @classmethod
    def from_env(cls) -> "SecretaryConfig":
        load_dotenv()
        return cls(
            api_base=os.getenv("PSEC_API_BASE", "http://localhost:5001"),
            api_key=os.getenv("PSEC_API_KEY") or None,
            stt_model=os.getenv("PSEC_STT_MODEL", "kcpp"),
            llm_model=os.getenv("PSEC_LLM_MODEL", "kcpp"),
            tts_model=os.getenv("PSEC_TTS_MODEL", "kcpp"),
            voice=os.getenv("PSEC_TTS_VOICE", "alloy"),
            sample_rate=int(os.getenv("PSEC_SAMPLE_RATE", "16000")),
            segment_seconds=int(os.getenv("PSEC_SEGMENT_SECONDS", "7")),
            audio_chunk_seconds=float(os.getenv("PSEC_AUDIO_CHUNK_SECONDS", "0.25")),
            vad_energy_threshold=float(os.getenv("PSEC_VAD_ENERGY_THRESHOLD", "0.006")),
            silence_gap_seconds=float(os.getenv("PSEC_SILENCE_GAP_SECONDS", "1.0")),
            min_speech_seconds=float(os.getenv("PSEC_MIN_SPEECH_SECONDS", "0.25")),
            max_turn_seconds=float(os.getenv("PSEC_MAX_TURN_SECONDS", "20.0")),
            partial_turn_seconds=float(os.getenv("PSEC_PARTIAL_TURN_SECONDS", "10.0")),
            partial_overlap_seconds=float(os.getenv("PSEC_PARTIAL_OVERLAP_SECONDS", "1.0")),
            partial_overlap_min_gap_seconds=float(os.getenv("PSEC_PARTIAL_OVERLAP_MIN_GAP_SECONDS", "0.3")),
            partial_overlap_max_seconds=float(os.getenv("PSEC_PARTIAL_OVERLAP_MAX_SECONDS", "2.0")),
            transcription_min_peak_level=float(os.getenv("PSEC_TRANSCRIPTION_MIN_PEAK_LEVEL", "0.004")),
            llm_merge_idle_seconds=float(os.getenv("PSEC_LLM_MERGE_IDLE_SECONDS", "0.75")),
            llm_merge_max_tokens=int(os.getenv("PSEC_LLM_MERGE_MAX_TOKENS", "1024")),
            llm_merge_max_sections=int(os.getenv("PSEC_LLM_MERGE_MAX_SECTIONS", "4")),
            llm_disable_thinking=os.getenv("PSEC_LLM_DISABLE_THINKING", "1").lower() in ("1", "true", "yes"),
            merge_lookback_sentences=int(os.getenv("PSEC_MERGE_LOOKBACK_SENTENCES", "1")),
            merge_lookback_words=int(os.getenv("PSEC_MERGE_LOOKBACK_WORDS", "40")),
            worker_poll_seconds=float(os.getenv("PSEC_WORKER_POLL_SECONDS", "0.05")),
            output_wav_path=os.getenv("PSEC_OUTPUT_WAV_PATH", "output.wav"),
            transcript_path=os.getenv("PSEC_TRANSCRIPT_PATH", "conversation.txt"),
            thought_log_path=os.getenv("PSEC_THOUGHT_LOG_PATH", "thoughts.log"),
            prototype_log_path=os.getenv("PSEC_PROTOTYPE_LOG_PATH", "prototype_transcript.log"),
            prototype_host=os.getenv("PSEC_PROTOTYPE_HOST", "127.0.0.1"),
            prototype_port=int(os.getenv("PSEC_PROTOTYPE_PORT", "8765")),
            request_timeout=float(os.getenv("PSEC_REQUEST_TIMEOUT", "120")),
            discovery_timeout=float(os.getenv("PSEC_DISCOVERY_TIMEOUT", "5")),
            debug=os.getenv("PSEC_DEBUG", "0").lower() in ("1", "true", "yes"),
        )

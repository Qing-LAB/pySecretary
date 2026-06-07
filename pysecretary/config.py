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
    output_wav_path: str = "output.wav"
    transcript_path: str = "conversation.txt"
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
            output_wav_path=os.getenv("PSEC_OUTPUT_WAV_PATH", "output.wav"),
            transcript_path=os.getenv("PSEC_TRANSCRIPT_PATH", "conversation.txt"),
            request_timeout=float(os.getenv("PSEC_REQUEST_TIMEOUT", "120")),
            discovery_timeout=float(os.getenv("PSEC_DISCOVERY_TIMEOUT", "5")),
            debug=os.getenv("PSEC_DEBUG", "0").lower() in ("1", "true", "yes"),
        )

from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient


class SpeechToTextClient:
    def __init__(self, config: SecretaryConfig, api: KoboldCppClient | None = None) -> None:
        self.config = config
        self.api = api or KoboldCppClient.from_config(config)

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        return self.api.transcribe_wav(
            audio_bytes=audio_bytes,
            model=self.config.stt_model,
        )

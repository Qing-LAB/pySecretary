from .audio import play_audio_bytes
from .config import SecretaryConfig
from .koboldcpp import KoboldCppClient


class TextToSpeechClient:
    def __init__(self, config: SecretaryConfig, api: KoboldCppClient | None = None) -> None:
        self.config = config
        self.api = api or KoboldCppClient.from_config(config)

    def synthesize(self, text: str) -> bytes:
        return self.api.synthesize_speech(
            text=text,
            model=self.config.tts_model,
            voice=self.config.voice,
        )

    def speak(self, text: str) -> None:
        audio_bytes = self.synthesize(text)
        play_audio_bytes(audio_bytes, self.config)

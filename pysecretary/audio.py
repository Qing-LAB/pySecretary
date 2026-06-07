import io

import numpy as np
import sounddevice as sd
import soundfile as sf

from .config import SecretaryConfig


def record_audio_segment(config: SecretaryConfig) -> bytes:
    """Record a short audio segment from the default microphone."""
    duration = config.segment_seconds
    samplerate = config.sample_rate
    channels = 1

    recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype="int16")
    sd.wait()

    with io.BytesIO() as buffer:
        sf.write(buffer, recording, samplerate, format="WAV", subtype="PCM_16")
        return buffer.getvalue()


def play_audio_bytes(audio_bytes: bytes, config: SecretaryConfig) -> None:
    """Play raw WAV bytes through the default audio output."""
    with io.BytesIO(audio_bytes) as buffer:
        data, samplerate = sf.read(buffer, dtype="int16")
        if data.size == 0:
            return
        sd.play(data, samplerate)
        sd.wait()

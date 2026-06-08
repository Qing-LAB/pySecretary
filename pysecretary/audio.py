import io
import math
import wave
from array import array
from dataclasses import dataclass
from threading import Event
from typing import Callable, Iterable, Iterator

try:
    import sounddevice as sd
except ImportError:
    sd = None

try:
    import soundfile as sf
except ImportError:
    sf = None

from .config import SecretaryConfig


@dataclass(frozen=True)
class AudioTurn:
    wav_bytes: bytes
    duration_seconds: float
    speech_seconds: float
    peak_level: float
    is_partial: bool = False


@dataclass
class AmplitudeVadConfig:
    """Amplitude VAD + turn-gate thresholds.

    Mutable so a single shared instance can be re-tuned at runtime (e.g. from the
    dashboard worker-options panel) while the capture loop keeps reading it per chunk.
    `transcription_min_peak_level` is the post-turn gate applied before STT.
    """

    sample_rate: int = 16000
    chunk_seconds: float = 0.25
    energy_threshold: float = 0.006
    silence_gap_seconds: float = 1.0
    min_speech_seconds: float = 0.25
    max_turn_seconds: float = 20.0
    partial_turn_seconds: float = 10.0
    partial_overlap_seconds: float = 1.0
    partial_overlap_min_gap_seconds: float = 0.3
    partial_overlap_max_seconds: float = 2.0
    transcription_min_peak_level: float = 0.004

    @classmethod
    def from_secretary_config(cls, config: SecretaryConfig) -> "AmplitudeVadConfig":
        return cls(
            sample_rate=config.sample_rate,
            chunk_seconds=config.audio_chunk_seconds,
            energy_threshold=config.vad_energy_threshold,
            silence_gap_seconds=config.silence_gap_seconds,
            min_speech_seconds=config.min_speech_seconds,
            max_turn_seconds=config.max_turn_seconds,
            partial_turn_seconds=config.partial_turn_seconds,
            partial_overlap_seconds=config.partial_overlap_seconds,
            partial_overlap_min_gap_seconds=config.partial_overlap_min_gap_seconds,
            partial_overlap_max_seconds=config.partial_overlap_max_seconds,
            transcription_min_peak_level=config.transcription_min_peak_level,
        )


def record_audio_segment(config: SecretaryConfig) -> bytes:
    """Record a short audio segment from the default microphone."""
    sounddevice = _require_dependency(sd, "sounddevice")
    soundfile = _require_dependency(sf, "soundfile")
    duration = config.segment_seconds
    samplerate = config.sample_rate
    channels = 1

    recording = sounddevice.rec(int(duration * samplerate), samplerate=samplerate, channels=channels, dtype="int16")
    sounddevice.wait()

    with io.BytesIO() as buffer:
        soundfile.write(buffer, recording, samplerate, format="WAV", subtype="PCM_16")
        return buffer.getvalue()


def play_audio_bytes(audio_bytes: bytes, config: SecretaryConfig) -> None:
    """Play raw WAV bytes through the default audio output."""
    sounddevice = _require_dependency(sd, "sounddevice")
    soundfile = _require_dependency(sf, "soundfile")
    with io.BytesIO(audio_bytes) as buffer:
        data, samplerate = soundfile.read(buffer, dtype="int16")
        if data.size == 0:
            return
        sounddevice.play(data, samplerate)
        sounddevice.wait()


class AudioTurnDetector:
    """Amplitude VAD that groups PCM chunks into significant speech turns."""

    def __init__(self, config: AmplitudeVadConfig) -> None:
        self.config = config
        self._chunks: list[bytes] = []
        self._in_speech = False
        self._duration_seconds = 0.0
        self._speech_seconds = 0.0
        self._silence_seconds = 0.0
        self._peak_level = 0.0
        self.last_level = 0.0
        self.last_is_speech = False

    @property
    def in_speech_turn(self) -> bool:
        return self._in_speech

    def accept_chunk(self, chunk: object) -> AudioTurn | None:
        pcm_bytes, sample_count = _chunk_to_pcm_bytes_and_count(chunk)
        if sample_count == 0:
            return None

        duration = sample_count / self.config.sample_rate
        level = _pcm_level(pcm_bytes)
        self.last_level = level

        speech = level >= self.config.energy_threshold
        self.last_is_speech = speech
        if speech and not self._in_speech:
            self._start_turn()

        if not self._in_speech:
            return None

        self._chunks.append(pcm_bytes)
        self._duration_seconds += duration
        self._peak_level = max(self._peak_level, level)

        if speech:
            self._speech_seconds += duration
            self._silence_seconds = 0.0
        else:
            self._silence_seconds += duration

        if self._silence_seconds >= self.config.silence_gap_seconds:
            return self._finish_if_significant()

        if self._duration_seconds >= self.config.max_turn_seconds:
            return self._finish_if_significant()

        # While a single long utterance is still going, flush a partial segment so STT and
        # cleanup can keep up in near real time instead of waiting for a pause. A short
        # trailing overlap is retained so boundary words are not cut between segments.
        partial_seconds = self.config.partial_turn_seconds
        if partial_seconds and self._duration_seconds >= partial_seconds:
            return self._flush_partial()

        return None

    def finish(self) -> AudioTurn | None:
        if not self._in_speech:
            return None
        return self._finish_if_significant()

    def _start_turn(self) -> None:
        self._chunks = []
        self._in_speech = True
        self._duration_seconds = 0.0
        self._speech_seconds = 0.0
        self._silence_seconds = 0.0
        self._peak_level = 0.0

    def _finish_if_significant(self) -> AudioTurn | None:
        chunks = self._chunks
        duration = self._duration_seconds
        speech_seconds = self._speech_seconds
        peak_level = self._peak_level
        self._reset()

        if speech_seconds < self.config.min_speech_seconds:
            return None

        return AudioTurn(
            wav_bytes=_pcm_chunks_to_wav(chunks, self.config.sample_rate),
            duration_seconds=duration,
            speech_seconds=speech_seconds,
            peak_level=peak_level,
        )

    def _flush_partial(self) -> AudioTurn | None:
        chunks = self._chunks
        duration = self._duration_seconds
        speech_seconds = self._speech_seconds
        peak_level = self._peak_level

        # The next segment re-starts from the most recent short pause (>= overlap_min_gap),
        # so the overlap begins at a natural boundary instead of mid-word. If no nearby pause
        # exists, fall back to a fixed trailing overlap.
        overlap_chunks = self._gap_overlap_chunks()
        if not overlap_chunks:
            overlap_chunks, _ = self._tail_chunks(self.config.partial_overlap_seconds)
        overlap_samples = sum(len(chunk) // 2 for chunk in overlap_chunks)
        overlap_duration = overlap_samples / self.config.sample_rate if self.config.sample_rate else 0.0
        self._chunks = list(overlap_chunks)
        self._duration_seconds = overlap_duration
        self._speech_seconds = overlap_duration
        self._silence_seconds = 0.0
        self._peak_level = max((_pcm_level(chunk) for chunk in overlap_chunks), default=0.0)
        # self._in_speech stays True so the utterance continues.

        if speech_seconds < self.config.min_speech_seconds:
            return None

        return AudioTurn(
            wav_bytes=_pcm_chunks_to_wav(chunks, self.config.sample_rate),
            duration_seconds=duration,
            speech_seconds=speech_seconds,
            peak_level=peak_level,
            is_partial=True,
        )

    def _gap_overlap_chunks(self) -> list[bytes]:
        index = self._gap_overlap_index()
        if index is None:
            return []
        return list(self._chunks[index:])

    def _gap_overlap_index(self) -> int | None:
        """Index of the start of the most recent short pause (>= overlap_min_gap) near the
        end, within the overlap_max window. Returns None if no such pause is nearby.
        """
        sample_rate = self.config.sample_rate
        min_gap = self.config.partial_overlap_min_gap_seconds
        max_window = self.config.partial_overlap_max_seconds
        if sample_rate <= 0 or min_gap <= 0:
            return None

        def chunk_seconds(chunk: bytes) -> float:
            return (len(chunk) // 2) / sample_rate

        scanned = 0.0
        index = len(self._chunks) - 1
        while index >= 0 and scanned <= max_window:
            chunk = self._chunks[index]
            if _pcm_level(chunk) < self.config.energy_threshold:
                # Measure the contiguous silence run ending at `index`.
                run_seconds = 0.0
                start = index
                while start >= 0 and _pcm_level(self._chunks[start]) < self.config.energy_threshold:
                    run_seconds += chunk_seconds(self._chunks[start])
                    start -= 1
                if run_seconds >= min_gap:
                    return start + 1  # start of the silence run
                scanned += run_seconds
                index = start
            else:
                scanned += chunk_seconds(chunk)
                index -= 1
        return None

    def _tail_chunks(self, seconds: float) -> tuple[list[bytes], int]:
        if seconds <= 0:
            return [], 0
        target_samples = int(seconds * self.config.sample_rate)
        kept: list[bytes] = []
        total = 0
        for chunk in reversed(self._chunks):
            kept.insert(0, chunk)
            total += len(chunk) // 2
            if total >= target_samples:
                break
        return kept, total

    def _reset(self) -> None:
        self._chunks = []
        self._in_speech = False
        self._duration_seconds = 0.0
        self._speech_seconds = 0.0
        self._silence_seconds = 0.0
        self._peak_level = 0.0


def listen_for_speech_turns(
    config: SecretaryConfig,
    stop_event: Event,
    on_audio_level: Callable[[float, bool, bool], None] | None = None,
    vad_config: "AmplitudeVadConfig | None" = None,
) -> Iterator[AudioTurn]:
    """Yield speech turns from the default microphone until stopped.

    A shared, mutable ``vad_config`` may be passed so thresholds can be re-tuned at
    runtime; otherwise one is built from ``config``.
    """
    sounddevice = _require_dependency(sd, "sounddevice")
    vad_config = vad_config or AmplitudeVadConfig.from_secretary_config(config)
    detector = AudioTurnDetector(vad_config)
    chunk_samples = max(1, int(vad_config.sample_rate * vad_config.chunk_seconds))

    while not stop_event.is_set():
        chunk = sounddevice.rec(
            chunk_samples,
            samplerate=vad_config.sample_rate,
            channels=1,
            dtype="int16",
        )
        sounddevice.wait()
        turn = detector.accept_chunk(chunk)
        if on_audio_level is not None:
            on_audio_level(detector.last_level, detector.last_is_speech, detector.in_speech_turn)
        if turn is not None:
            yield turn

    final_turn = detector.finish()
    if final_turn is not None:
        yield final_turn


def _chunk_to_pcm_bytes_and_count(chunk: object) -> tuple[bytes, int]:
    if isinstance(chunk, bytes):
        return chunk, len(chunk) // 2
    if isinstance(chunk, bytearray):
        pcm = bytes(chunk)
        return pcm, len(pcm) // 2
    if hasattr(chunk, "tobytes") and hasattr(chunk, "size"):
        pcm = chunk.tobytes()
        return pcm, len(pcm) // 2

    values = list(_flatten_samples(chunk))
    pcm_array = array("h", [int(_clip_int16(value)) for value in values])
    return pcm_array.tobytes(), len(pcm_array)


def _flatten_samples(chunk: object) -> Iterable[int | float]:
    if hasattr(chunk, "tolist"):
        yield from _flatten_samples(chunk.tolist())
        return
    if isinstance(chunk, (list, tuple)):
        for item in chunk:
            yield from _flatten_samples(item)
        return
    yield int(chunk)  # type: ignore[arg-type]


def _clip_int16(value: int | float) -> int:
    return max(-32768, min(32767, int(value)))


def _pcm_level(pcm_bytes: bytes) -> float:
    if not pcm_bytes:
        return 0.0

    samples = array("h")
    samples.frombytes(pcm_bytes)
    if not samples:
        return 0.0

    square_sum = sum(sample * sample for sample in samples)
    rms = math.sqrt(square_sum / len(samples))
    return min(1.0, rms / 32768.0)


def _pcm_chunks_to_wav(chunks: list[bytes], sample_rate: int) -> bytes:
    with io.BytesIO() as buffer:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"".join(chunks))
        return buffer.getvalue()


def _require_dependency(dependency: object | None, name: str) -> object:
    if dependency is None:
        raise RuntimeError(
            f"{name} is required for live audio. Install project dependencies with `pip install -r requirements.txt`."
        )
    return dependency

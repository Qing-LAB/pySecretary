from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeAudioData:
    size: int = 1


@dataclass
class AudioStubState:
    rec_calls: list[dict[str, Any]] = field(default_factory=list)
    play_calls: list[dict[str, Any]] = field(default_factory=list)
    write_calls: list[dict[str, Any]] = field(default_factory=list)
    read_calls: list[dict[str, Any]] = field(default_factory=list)
    wait_count: int = 0
    recording: Any = "recording"
    playback_data: FakeAudioData = field(default_factory=FakeAudioData)
    playback_samplerate: int = 22050


def install_audio_dependency_stubs() -> AudioStubState:
    state = AudioStubState()

    sounddevice = types.ModuleType("sounddevice")

    def rec(samples: int, *, samplerate: int, channels: int, dtype: str) -> Any:
        state.rec_calls.append(
            {
                "samples": samples,
                "samplerate": samplerate,
                "channels": channels,
                "dtype": dtype,
            }
        )
        return state.recording

    def wait() -> None:
        state.wait_count += 1

    def play(data: Any, samplerate: int) -> None:
        state.play_calls.append({"data": data, "samplerate": samplerate})

    sounddevice.rec = rec
    sounddevice.wait = wait
    sounddevice.play = play

    soundfile = types.ModuleType("soundfile")

    def write(buffer: Any, recording: Any, samplerate: int, *, format: str, subtype: str) -> None:
        state.write_calls.append(
            {
                "recording": recording,
                "samplerate": samplerate,
                "format": format,
                "subtype": subtype,
            }
        )
        buffer.write(b"fake-wav")

    def read(buffer: Any, *, dtype: str) -> tuple[FakeAudioData, int]:
        state.read_calls.append({"dtype": dtype, "bytes": buffer.getvalue()})
        return state.playback_data, state.playback_samplerate

    soundfile.write = write
    soundfile.read = read

    numpy = types.ModuleType("numpy")

    sys.modules["sounddevice"] = sounddevice
    sys.modules["soundfile"] = soundfile
    sys.modules["numpy"] = numpy
    sys.modules.pop("pysecretary.audio", None)
    sys.modules.pop("pysecretary.tts", None)

    return state


from __future__ import annotations

import sys
import threading
from typing import Callable, Protocol, TextIO, runtime_checkable


@runtime_checkable
class TranscriptSink(Protocol):
    """Delivers finalized spoken text to an external target (another program)."""

    def deliver(self, text: str) -> None:
        ...


class StdoutSink:
    """Writes each delivered utterance as a line to a stream (pipe into another program).

    Use as ``pysecretary … | yourprogram`` so the program reads utterances on its stdin.
    """

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def deliver(self, text: str) -> None:
        self._stream.write(text.rstrip("\n") + "\n")
        self._stream.flush()


class ClipboardSink:
    """Copies each utterance to the system clipboard, optionally auto-pasting it.

    Requires ``pyperclip`` (clipboard) and, for auto-paste, ``pynput`` (sends Ctrl+V to the
    focused window). Imports are lazy so the rest of the app does not depend on them.
    """

    def __init__(self, auto_paste: bool = False) -> None:
        self.auto_paste = auto_paste

    def deliver(self, text: str) -> None:
        import pyperclip

        pyperclip.copy(text)
        if self.auto_paste:
            from pynput.keyboard import Controller, Key

            keyboard = Controller()
            with keyboard.pressed(Key.ctrl):
                keyboard.press("v")
                keyboard.release("v")


class KeystrokeSink:
    """Types each utterance into the currently focused window via ``pynput`` (lazy import)."""

    def deliver(self, text: str) -> None:
        from pynput.keyboard import Controller

        Controller().type(text)


def make_sink(name: str, *, auto_paste: bool = False) -> TranscriptSink | None:
    """Build a sink by name, or ``None`` for an empty/``"none"`` name."""
    normalized = (name or "").strip().lower()
    if normalized in ("", "none"):
        return None
    if normalized == "stdout":
        return StdoutSink()
    if normalized == "clipboard":
        return ClipboardSink(auto_paste=auto_paste)
    if normalized == "keystroke":
        return KeystrokeSink()
    raise ValueError(f"Unknown output sink: {name!r} (expected stdout, clipboard, or keystroke)")


class OutputHotkeyListener:
    """Global hotkey that triggers push-to-send even when another window is focused.

    Uses ``pynput`` (lazy import). The hotkey string uses pynput syntax, e.g.
    ``"<ctrl>+<alt>+s"``. Best-effort: if pynput is unavailable it does nothing.
    """

    def __init__(self, hotkey: str, on_trigger: Callable[[], None]) -> None:
        self.hotkey = hotkey
        self._on_trigger = on_trigger
        self._listener: object | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        if not self.hotkey:
            return False
        try:
            from pynput import keyboard
        except ImportError:
            return False
        with self._lock:
            if self._listener is not None:
                return True
            listener = keyboard.GlobalHotKeys({self.hotkey: self._on_trigger})
            listener.start()
            self._listener = listener
        return True

    def stop(self) -> None:
        with self._lock:
            listener = self._listener
            self._listener = None
        if listener is not None:
            stop = getattr(listener, "stop", None)
            if callable(stop):
                stop()

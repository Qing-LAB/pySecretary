import re

from .config import SecretaryConfig
from .koboldcpp import KoboldCppApi, KoboldCppClient


NON_SPEECH_TRANSCRIPTS = {
    "blankaudio",
    "blank",
    "nospeech",
    "nospeechdetected",
    "nonspeech",
    "silence",
    "silent",
}

ARTIFACT_WORDS = {
    "ambient",
    "applause",
    "audience",
    "audio",
    "background",
    "bang",
    "banging",
    "beep",
    "beeping",
    "bell",
    "bird",
    "birds",
    "blank",
    "breathing",
    "buzz",
    "buzzing",
    "camera",
    "chatter",
    "cheering",
    "chime",
    "clap",
    "clapping",
    "clatter",
    "click",
    "clicking",
    "cough",
    "coughing",
    "coughs",
    "crackle",
    "creak",
    "crowd",
    "door",
    "drum",
    "engine",
    "exhale",
    "exhales",
    "footsteps",
    "gasp",
    "groan",
    "honk",
    "horn",
    "hum",
    "humming",
    "inaudible",
    "inhale",
    "inhales",
    "instrumental",
    "knock",
    "knocking",
    "laugh",
    "laughing",
    "laughs",
    "laughter",
    "machine",
    "motor",
    "mumble",
    "mumbling",
    "music",
    "noise",
    "noises",
    "phone",
    "pop",
    "rain",
    "rattle",
    "ring",
    "ringing",
    "ringtone",
    "rumble",
    "rustle",
    "scream",
    "screaming",
    "screech",
    "shutter",
    "sigh",
    "sighs",
    "silence",
    "siren",
    "sneeze",
    "snoring",
    "sound",
    "sounds",
    "splash",
    "squeak",
    "static",
    "thud",
    "thunder",
    "tone",
    "traffic",
    "typing",
    "unintelligible",
    "upbeat",
    "vibrate",
    "vibrating",
    "vibration",
    "whir",
    "whirring",
    "whisper",
    "whispering",
    "whistle",
    "wind",
    "yawn",
}

ARTIFACT_FILLER_WORDS = {
    "a",
    "an",
    "and",
    "at",
    "by",
    "from",
    "in",
    "of",
    "on",
    "the",
    "to",
}


class SpeechToTextClient:
    def __init__(self, config: SecretaryConfig, api: KoboldCppApi | None = None) -> None:
        self.config = config
        self.api = api or KoboldCppClient.from_config(config)

    def transcribe_audio(self, audio_bytes: bytes) -> str:
        return self.api.transcribe_wav(
            audio_bytes=audio_bytes,
            model=self.config.stt_model,
            suppress_non_speech=True,
        )


def is_non_speech_transcript(text: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", text.lower())
    return normalized in NON_SPEECH_TRANSCRIPTS


def is_non_content_transcript(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True

    if is_non_speech_transcript(stripped):
        return True

    cue_text = _strip_wrapping_cue_marks(stripped)
    if cue_text == stripped:
        return False

    words = re.findall(r"[a-z]+", cue_text.lower())
    if not words:
        return True

    meaningful_words = [word for word in words if word not in ARTIFACT_FILLER_WORDS]
    if not meaningful_words:
        return True

    return all(word in ARTIFACT_WORDS for word in meaningful_words)


_CUE_SEGMENT_PATTERNS = (
    re.compile(r"\([^()]*\)"),
    re.compile(r"\[[^\[\]]*\]"),
    re.compile(r"\{[^{}]*\}"),
    re.compile(r"♪[^♪]*♪"),
    re.compile(r"♪+"),
    re.compile(r"♫+"),
)


def clean_transcript_artifacts(text: str) -> str:
    """Strip embedded non-speech sound cues from STT output.

    Whisper-style transcription frequently injects bracketed or parenthesized sound
    captions such as ``(coughing)``, ``[door closes]``, or ``♪ music ♪`` even inside
    otherwise valid speech. These confuse the cleanup LLM, so they are removed before the
    text reaches the merge worker. Real parentheticals (whose words are not all
    background-noise terms) are preserved.
    """
    if not text:
        return ""

    cleaned = text
    for pattern in _CUE_SEGMENT_PATTERNS:
        cleaned = pattern.sub(_drop_cue_segment, cleaned)

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    return cleaned.strip().strip("-–—").strip()


def _drop_cue_segment(match: "re.Match[str]") -> str:
    return "" if _segment_is_artifact(match.group(0)) else match.group(0)


def _segment_is_artifact(segment: str) -> bool:
    words = re.findall(r"[a-z]+", segment.lower())
    if not words:
        return True

    meaningful_words = [word for word in words if word not in ARTIFACT_FILLER_WORDS]
    if not meaningful_words:
        return True

    return all(word in ARTIFACT_WORDS for word in meaningful_words)


def _strip_wrapping_cue_marks(text: str) -> str:
    stripped = text.strip()
    pairs = {
        "(": ")",
        "[": "]",
        "{": "}",
    }
    closing = pairs.get(stripped[:1])
    if closing and stripped.endswith(closing):
        return stripped[1:-1].strip()

    if stripped.startswith("<") and stripped.endswith(">"):
        return stripped[1:-1].strip()

    if stripped.startswith("♪") and stripped.endswith("♪"):
        return stripped.strip("♪").strip()

    return stripped

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
    "distant",
    "faint",
    "gentle",
    "loud",
    "soft",
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


def dedup_overlap(previous_text: str, next_text: str, max_overlap_words: int = 15) -> str:
    """Trim a leading run of words from ``next_text`` that duplicates the end of
    ``previous_text``.

    Consecutive STT sections share a few words because audio is captured with overlap, so
    the start of one section repeats the end of the previous (e.g. "...to the" + "to the
    meeting..."). This removes that duplicated prefix at the word level (case- and
    punctuation-insensitive), keeping the original text of the words that are kept.
    """
    next_tokens = re.findall(r"\S+", next_text)
    prev_norm = [_dedup_norm(token) for token in re.findall(r"\S+", previous_text)]
    prev_norm = [token for token in prev_norm if token]
    next_norm = [_dedup_norm(token) for token in next_tokens]

    max_k = min(max_overlap_words, len(prev_norm), len(next_norm))
    for k in range(max_k, 0, -1):
        # Compare against the non-empty normalized prefix of next, but trim the original
        # tokens by the same count.
        if prev_norm[-k:] == [t for t in next_norm if t][:k]:
            kept = 0
            seen = 0
            for index, token in enumerate(next_norm):
                if token:
                    seen += 1
                if seen >= k:
                    kept = index + 1
                    break
            return " ".join(next_tokens[kept:]).lstrip()
    return next_text


def _dedup_norm(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", token.lower())


def trim_repeated_prefix(reference: str, text: str, min_match_words: int = 3) -> str:
    """Trim a leading run of ``text`` that duplicates any contiguous run inside ``reference``.

    Unlike :func:`dedup_overlap` (which only matches a suffix of the previous text), this
    catches a section that *restarts* from the middle of the reference — e.g. the model
    re-emits part of the editable tail when it (wrongly) opens a new paragraph. Only a match
    of at least ``min_match_words`` words is trimmed, to avoid removing incidental repeats.
    """
    ref_norm = [token for token in (_dedup_norm(t) for t in re.findall(r"\S+", reference)) if token]
    text_tokens = re.findall(r"\S+", text)
    text_norm = [_dedup_norm(token) for token in text_tokens]
    non_empty = [token for token in text_norm if token]
    if len(ref_norm) < min_match_words or len(non_empty) < min_match_words:
        return text

    max_k = min(len(ref_norm), len(non_empty))
    for k in range(max_k, min_match_words - 1, -1):
        prefix = non_empty[:k]
        if _contains_run(ref_norm, prefix):
            kept = 0
            seen = 0
            for index, token in enumerate(text_norm):
                if token:
                    seen += 1
                if seen >= k:
                    kept = index + 1
                    break
            return " ".join(text_tokens[kept:]).lstrip()
    return text


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    for start in range(len(haystack) - len(needle) + 1):
        if haystack[start : start + len(needle)] == needle:
            return True
    return False


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

    # Asterisk-wrapped stage directions (e.g. "*clicks*", "*laughs*") are always sound/action
    # cues from the transcriber, never spoken content.
    cleaned = re.sub(r"\*[^*\n]+\*", "", cleaned)

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

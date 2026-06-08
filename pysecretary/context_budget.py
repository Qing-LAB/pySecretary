from __future__ import annotations

import re


_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]?\s+")


def split_recent_tail(text: str, max_sentences: int, max_words: int) -> tuple[str, str]:
    """Split text into a frozen head and a small re-editable tail.

    The tail is the last `max_sentences` sentences, capped to at most `max_words` words
    (whichever yields the shorter tail), so only a bounded recent slice stays "hot" while
    everything older is frozen. The last sentence may be incomplete; that is intentional —
    the caller lets the model decide whether new speech completes it or starts anew.
    """
    if not text.strip():
        return "", ""

    starts = [0] + [match.end() for match in _SENTENCE_END_RE.finditer(text)]
    starts = [start for start in starts if text[start:].strip()]
    if not starts:
        starts = [0]

    if max_sentences > 0 and len(starts) > max_sentences:
        boundary_by_sentence = starts[-max_sentences]
    else:
        boundary_by_sentence = 0

    boundary_by_words = _word_boundary_from_end(text, max_words)
    boundary = max(boundary_by_sentence, boundary_by_words)
    return text[:boundary], text[boundary:]


def _word_boundary_from_end(text: str, max_words: int) -> int:
    if max_words <= 0:
        return 0
    words = list(re.finditer(r"\S+", text))
    if len(words) <= max_words:
        return 0
    return words[-max_words].start()


def combine_stable_prefix(stable_prefix: str, cleaned_tail: str) -> str:
    """Join a frozen head and a (re)cleaned tail/region on a sentence-aware separator."""
    prefix = stable_prefix.strip()
    tail = cleaned_tail.strip()
    if not prefix:
        return tail
    if not tail:
        return prefix
    separator = "\n" if prefix.endswith((".", "!", "?", ":", ";")) else " "
    return f"{prefix}{separator}{tail}"

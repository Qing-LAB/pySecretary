from __future__ import annotations

from dataclasses import dataclass


APPROX_CHARS_PER_TOKEN = 4


@dataclass(frozen=True)
class PreparedMergeContext:
    existing_smoothed_text: str
    stable_prefix: str
    recent_raw_context: str
    current_context_summary: str
    new_raw_text: str
    context_limit_tokens: int
    available_input_tokens: int
    estimated_input_tokens: int
    support_was_reduced: bool = False
    latest_exceeds_budget: bool = False


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + APPROX_CHARS_PER_TOKEN - 1) // APPROX_CHARS_PER_TOKEN)


def prepare_merge_context(
    existing_smoothed_text: str,
    recent_raw_context: str,
    current_context_summary: str,
    new_raw_text: str,
    context_limit_tokens: int,
    response_reserved_tokens: int,
    safety_tokens: int,
    prompt_overhead_tokens: int,
) -> PreparedMergeContext:
    available = max(0, context_limit_tokens - response_reserved_tokens - safety_tokens - prompt_overhead_tokens)
    latest_tokens = estimate_tokens(new_raw_text)
    support_budget = max(0, available - latest_tokens)

    if latest_tokens >= available:
        return PreparedMergeContext(
            existing_smoothed_text="",
            stable_prefix=existing_smoothed_text,
            recent_raw_context="",
            current_context_summary="",
            new_raw_text=new_raw_text,
            context_limit_tokens=context_limit_tokens,
            available_input_tokens=available,
            estimated_input_tokens=latest_tokens,
            support_was_reduced=bool(existing_smoothed_text or recent_raw_context or current_context_summary),
            latest_exceeds_budget=True,
        )

    context_budget = min(512, max(0, support_budget // 5))
    recent_budget = min(512, max(0, support_budget // 5))
    existing_budget = max(0, support_budget - context_budget - recent_budget)

    if existing_smoothed_text and existing_budget < 256 and support_budget >= 256:
        existing_budget = min(support_budget, 256)
        remaining = max(0, support_budget - existing_budget)
        context_budget = min(context_budget, remaining // 2)
        recent_budget = max(0, remaining - context_budget)

    stable_prefix, existing_tail = split_stable_prefix(existing_smoothed_text, existing_budget)
    compact_context = tail_to_token_budget(current_context_summary, context_budget)
    compact_recent = tail_to_token_budget(recent_raw_context, recent_budget)
    estimated = (
        estimate_tokens(existing_tail)
        + estimate_tokens(compact_context)
        + estimate_tokens(compact_recent)
        + latest_tokens
    )

    return PreparedMergeContext(
        existing_smoothed_text=existing_tail,
        stable_prefix=stable_prefix,
        recent_raw_context=compact_recent,
        current_context_summary=compact_context,
        new_raw_text=new_raw_text,
        context_limit_tokens=context_limit_tokens,
        available_input_tokens=available,
        estimated_input_tokens=estimated,
        support_was_reduced=(
            stable_prefix != ""
            or compact_context != current_context_summary
            or compact_recent != recent_raw_context
        ),
        latest_exceeds_budget=False,
    )


def split_stable_prefix(text: str, tail_budget_tokens: int) -> tuple[str, str]:
    if not text or estimate_tokens(text) <= tail_budget_tokens:
        return "", text
    if tail_budget_tokens <= 0:
        return text.rstrip(), ""

    tail_char_budget = tail_budget_tokens * APPROX_CHARS_PER_TOKEN
    cut = max(0, len(text) - tail_char_budget)
    boundary = _find_forward_boundary(text, cut)
    if boundary is None or boundary >= len(text):
        boundary = cut

    return text[:boundary].rstrip(), text[boundary:].lstrip()


def tail_to_token_budget(text: str, budget_tokens: int) -> str:
    if not text or estimate_tokens(text) <= budget_tokens:
        return text
    if budget_tokens <= 0:
        return ""

    char_budget = budget_tokens * APPROX_CHARS_PER_TOKEN
    cut = max(0, len(text) - char_budget)
    boundary = _find_forward_boundary(text, cut)
    if boundary is None or boundary >= len(text):
        boundary = cut
    tail = text[boundary:].lstrip()
    return f"[older support context omitted]\n{tail}" if tail else ""


def combine_stable_prefix(stable_prefix: str, cleaned_tail: str) -> str:
    prefix = stable_prefix.strip()
    tail = cleaned_tail.strip()
    if not prefix:
        return tail
    if not tail:
        return prefix
    separator = "\n" if prefix.endswith((".", "!", "?", ":", ";")) else " "
    return f"{prefix}{separator}{tail}"


def _find_forward_boundary(text: str, start: int) -> int | None:
    candidates = []
    for marker in ("\n\n", "\n", ". ", "? ", "! ", "; ", ", ", " "):
        index = text.find(marker, start)
        if index != -1:
            candidates.append(index + len(marker))
    return min(candidates) if candidates else None

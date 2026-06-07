import unittest

from pysecretary.context_budget import (
    combine_stable_prefix,
    estimate_tokens,
    prepare_merge_context,
)


class ContextBudgetTests(unittest.TestCase):
    def test_estimator_uses_conservative_character_ratio(self) -> None:
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("abcde"), 2)

    def test_prepare_merge_context_preserves_latest_raw_text_and_reduces_support(self) -> None:
        latest = '{"transcript_sections": [{"raw_text": "latest original words"}]}'
        prepared = prepare_merge_context(
            existing_smoothed_text="old sentence. " * 200,
            recent_raw_context="recent raw. " * 100,
            current_context_summary="context summary. " * 100,
            new_raw_text=latest,
            context_limit_tokens=180,
            response_reserved_tokens=40,
            safety_tokens=20,
            prompt_overhead_tokens=40,
        )

        self.assertEqual(prepared.new_raw_text, latest)
        self.assertTrue(prepared.support_was_reduced)
        self.assertTrue(prepared.stable_prefix)
        self.assertLess(prepared.estimated_input_tokens, 180)

    def test_latest_sections_are_preserved_even_when_they_exceed_available_budget(self) -> None:
        latest = '{"raw_text": "' + ("latest " * 300) + '"}'
        prepared = prepare_merge_context(
            existing_smoothed_text="old text",
            recent_raw_context="recent",
            current_context_summary="context",
            new_raw_text=latest,
            context_limit_tokens=80,
            response_reserved_tokens=20,
            safety_tokens=10,
            prompt_overhead_tokens=20,
        )

        self.assertEqual(prepared.new_raw_text, latest)
        self.assertEqual(prepared.existing_smoothed_text, "")
        self.assertEqual(prepared.recent_raw_context, "")
        self.assertEqual(prepared.current_context_summary, "")
        self.assertTrue(prepared.latest_exceeds_budget)

    def test_combine_stable_prefix_uses_original_prefix_text(self) -> None:
        self.assertEqual(
            combine_stable_prefix("Original prefix.", "Cleaned latest."),
            "Original prefix.\nCleaned latest.",
        )


if __name__ == "__main__":
    unittest.main()

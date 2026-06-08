import unittest

from pysecretary.context_budget import combine_stable_prefix, split_recent_tail


class ContextBudgetTests(unittest.TestCase):
    def test_split_recent_tail_keeps_last_sentence_editable(self) -> None:
        head, tail = split_recent_tail("First sentence. Second part still going", max_sentences=1, max_words=40)
        self.assertEqual(head, "First sentence. ")
        self.assertEqual(tail, "Second part still going")

    def test_split_recent_tail_caps_by_words(self) -> None:
        text = "one two three four five six seven eight"
        head, tail = split_recent_tail(text, max_sentences=1, max_words=3)
        # No sentence boundary, so the word cap keeps only the last 3 words editable.
        self.assertEqual(tail, "six seven eight")
        self.assertEqual(head, "one two three four five ")

    def test_split_recent_tail_word_cap_overrides_long_sentence(self) -> None:
        # A long final sentence is still bounded to the word cap (shorter tail wins).
        text = "a b c d e f g h i j."
        _head, tail = split_recent_tail(text, max_sentences=1, max_words=3)
        self.assertEqual(tail, "h i j.")

    def test_split_recent_tail_handles_empty(self) -> None:
        self.assertEqual(split_recent_tail("", 1, 40), ("", ""))

    def test_combine_stable_prefix_uses_original_prefix_text(self) -> None:
        self.assertEqual(
            combine_stable_prefix("Original prefix.", "Cleaned latest."),
            "Original prefix.\nCleaned latest.",
        )

    def test_combine_stable_prefix_joins_mid_sentence_with_space(self) -> None:
        # A head ending mid-sentence (no terminal punctuation) continues with a space.
        self.assertEqual(combine_stable_prefix("the meeting is", "at noon"), "the meeting is at noon")

    def test_combine_stable_prefix_handles_empty_sides(self) -> None:
        self.assertEqual(combine_stable_prefix("", "tail"), "tail")
        self.assertEqual(combine_stable_prefix("head", ""), "head")


if __name__ == "__main__":
    unittest.main()

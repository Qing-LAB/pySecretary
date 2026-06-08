import json
import unittest

from pysecretary.config import SecretaryConfig
from pysecretary.koboldcpp import KoboldCppProfile
from pysecretary.transcript import (
    LLMTranscriptMerger,
    TranscriptSection,
    format_transcript_sections_for_prompt,
    parse_merge_response,
    split_thought_text,
)


class FakeMergeLlm:
    def __init__(self, response: str, config: SecretaryConfig | None = None, profile: KoboldCppProfile | None = None) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []
        self.config = config
        self.api = type("FakeApi", (), {"profile": profile})()

    def merge_transcript_context(
        self,
        existing_smoothed_text: str,
        new_raw_text: str,
        recent_raw_context: str = "",
        current_context_summary: str = "",
        prior_transcript_was_reduced: bool = False,
    ) -> str:
        self.calls.append(
            {
                "existing": existing_smoothed_text,
                "new_raw": new_raw_text,
                "recent_raw": recent_raw_context,
                "context": current_context_summary,
                "reduced": str(prior_transcript_was_reduced),
            }
        )
        return self.response


def make_section(
    turn_id: str = "turn-a",
    sequence: int = 1,
    text: str = "raw words",
) -> TranscriptSection:
    return TranscriptSection(
        turn_id=turn_id,
        sequence=sequence,
        text=text,
        captured_at=10.0 + sequence,
        transcribed_at=11.0 + sequence,
        duration_seconds=1.2,
        speech_seconds=0.9,
        peak_level=0.4,
    )


class TranscriptMergeTests(unittest.TestCase):
    def test_split_thought_text_removes_complete_and_open_think_blocks(self) -> None:
        split = split_thought_text("final before <think>hidden one</think> final after <think>hidden two")

        self.assertEqual(split.final_text, "final before  final after")
        self.assertEqual(split.thoughts, ["hidden one", "hidden two"])

    def test_parse_merge_response_handles_json_and_thoughts(self) -> None:
        response = (
            "<think>compare raw to context</think>\n"
            '{"smoothed_text": "The user described the prototype.", "feedback": ["removed filler"], '
            '"context_summary": "Prototype discussion.", "context_action": "continue"}'
        )

        result = parse_merge_response(response)

        self.assertEqual(result.smoothed_text, "The user described the prototype.")
        self.assertEqual(result.feedback, ["removed filler"])
        self.assertEqual(result.thoughts, ["compare raw to context"])
        self.assertEqual(result.context_summary, "Prototype discussion.")
        self.assertEqual(result.context_action, "continue")

    def test_parse_merge_response_normalizes_context_renewal(self) -> None:
        result = parse_merge_response(
            '{"smoothed_text": "New topic.", "context_summary": "New topic.", "context_action": "new_conversation"}'
        )

        self.assertEqual(result.context_action, "renew")
        self.assertEqual(result.context_summary, "New topic.")

    def test_parse_merge_response_falls_back_to_plain_text(self) -> None:
        result = parse_merge_response("Plain smoothed transcript.")

        self.assertEqual(result.smoothed_text, "Plain smoothed transcript.")
        self.assertEqual(result.feedback, [])
        self.assertEqual(result.thoughts, [])

    def test_llm_merger_passes_context_and_separates_output(self) -> None:
        llm = FakeMergeLlm('{"smoothed_text": "Updated text", "feedback": "merged turn"}')
        merger = LLMTranscriptMerger(llm)  # type: ignore[arg-type]
        section = make_section(text="um new words")

        result = merger.merge("Existing", [section], "older raw", current_context_summary="prototype context")

        self.assertEqual(result.smoothed_text, "Updated text")
        self.assertEqual(result.feedback, ["merged turn"])
        self.assertEqual(llm.calls[0]["existing"], "Existing")
        self.assertIn('"raw_text": "um new words"', llm.calls[0]["new_raw"])
        self.assertIn('"section": 1', llm.calls[0]["new_raw"])
        self.assertEqual(llm.calls[0]["recent_raw"], "older raw")
        self.assertEqual(llm.calls[0]["context"], "prototype context")
        self.assertEqual(llm.calls[0]["reduced"], "False")

    def test_llm_merger_passes_editable_tail_and_returns_region(self) -> None:
        # The merger passes the controller-chosen editable tail through unchanged and
        # returns whatever the model produced (the spliced region); the controller decides
        # how to splice it back. Tail bounding is the controller's job (split_recent_tail).
        llm = FakeMergeLlm('{"smoothed_text": "Editable tail completed by the new words."}')
        merger = LLMTranscriptMerger(llm)  # type: ignore[arg-type]
        section = make_section(text="completed by the new words")

        result = merger.merge("Editable tail", [section], "recent raw", "current context")

        self.assertEqual(result.smoothed_text, "Editable tail completed by the new words.")
        self.assertEqual(llm.calls[0]["existing"], "Editable tail")
        self.assertIn('"raw_text": "completed by the new words"', llm.calls[0]["new_raw"])

    def test_parse_merge_response_normalizes_paragraph_action(self) -> None:
        result = parse_merge_response('{"smoothed_text": "x", "context_action": "new_paragraph"}')
        self.assertEqual(result.context_action, "paragraph")

    def test_format_transcript_sections_for_prompt_serializes_ordered_metadata(self) -> None:
        payload = json.loads(
            format_transcript_sections_for_prompt(
                [
                    make_section(turn_id="a", sequence=1, text="first"),
                    make_section(turn_id="b", sequence=2, text="actually second correction"),
                ]
            )
        )

        sections = payload["transcript_sections"]
        self.assertEqual([section["section"] for section in sections], [1, 2])
        self.assertEqual(sections[0]["raw_text"], "first")
        self.assertEqual(sections[1]["raw_text"], "actually second correction")
        self.assertEqual(sections[0]["duration_seconds"], 1.2)


if __name__ == "__main__":
    unittest.main()

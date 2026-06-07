import unittest

from pysecretary.events import AssistantCommand, PrototypeState, make_event, reduce_prototype_state


class EventContractTests(unittest.TestCase):
    def test_event_and_command_are_json_ready_dicts(self) -> None:
        event = make_event("RawTranscriptReceived", turn_id="t1", text="raw text")
        command = AssistantCommand(type="StartAutomaticCapture")

        self.assertEqual(event.to_dict()["type"], "RawTranscriptReceived")
        self.assertEqual(event.to_dict()["payload"]["text"], "raw text")
        self.assertEqual(command.to_dict(), {"type": "StartAutomaticCapture", "payload": {}})

    def test_reducer_keeps_raw_smoothed_feedback_and_thoughts_separate(self) -> None:
        state = PrototypeState()

        reduce_prototype_state(state, make_event("RecordingStarted"))
        reduce_prototype_state(state, make_event("AudioLevelChanged", level=0.04, speech_detected=True, in_speech_turn=True))
        reduce_prototype_state(state, make_event("SpeechTurnDiscarded", turn_id="t0", reason="low_peak_level", peak_level=0.01))
        reduce_prototype_state(state, make_event("RawTranscriptReceived", turn_id="t1", text="um raw"))
        reduce_prototype_state(state, make_event("TranscriptionDiscarded", turn_id="t2", text="BLANK_AUDIO", reason="non_speech_sentinel"))
        reduce_prototype_state(state, make_event("ThoughtCaptured", turn_id="t1", text="debug reasoning"))
        reduce_prototype_state(state, make_event("MergeFeedbackReceived", turn_id="t1", text="removed filler"))
        reduce_prototype_state(
            state,
            make_event(
                "SmoothedTranscriptUpdated",
                turn_id="t1",
                text="raw",
                context_summary="dictation context",
                context_action="continue",
            ),
        )

        self.assertTrue(state.running)
        self.assertEqual(state.status, "listening")
        self.assertEqual(state.last_audio_level, 0.04)
        self.assertTrue(state.audio_detected)
        self.assertTrue(state.in_speech_turn)
        self.assertEqual(state.discarded_turns[0]["reason"], "low_peak_level")
        self.assertEqual(state.raw_transcripts[0]["text"], "um raw")
        self.assertEqual(state.discarded_transcriptions[0]["text"], "BLANK_AUDIO")
        self.assertEqual(state.discarded_transcriptions[0]["reason"], "non_speech_sentinel")
        self.assertEqual(state.thoughts[0]["text"], "debug reasoning")
        self.assertEqual(state.feedback[0]["text"], "removed filler")
        self.assertEqual(state.smoothed_text, "raw")
        self.assertEqual(state.context_summary, "dictation context")
        self.assertEqual(state.context_action, "continue")
        self.assertNotIn("debug reasoning", state.smoothed_text)

    def test_reducer_renews_context_summary(self) -> None:
        state = PrototypeState(context_summary="old topic", context_action="continue")

        reduce_prototype_state(
            state,
            make_event(
                "SmoothedTranscriptUpdated",
                text="new topic text",
                context_summary="new topic",
                context_action="renew",
            ),
        )

        self.assertEqual(state.context_summary, "new topic")
        self.assertEqual(state.context_action, "renew")

    def test_reducer_can_clear_context_on_renew(self) -> None:
        state = PrototypeState(context_summary="old topic", context_action="continue")

        reduce_prototype_state(
            state,
            make_event("SmoothedTranscriptUpdated", text="new text", context_summary="", context_action="renew"),
        )

        self.assertEqual(state.context_summary, "")
        self.assertEqual(state.context_action, "renew")

    def test_clear_event_resets_transcript_panels(self) -> None:
        state = PrototypeState(smoothed_text="old", context_summary="context", context_action="renew")
        state.raw_transcripts.append({"text": "raw"})
        state.discarded_turns.append({"reason": "low_peak_level"})
        state.discarded_transcriptions.append({"text": "BLANK_AUDIO"})
        state.feedback.append({"text": "note"})
        state.thoughts.append({"text": "thought"})

        reduce_prototype_state(state, make_event("PrototypeTranscriptCleared"))

        self.assertEqual(state.smoothed_text, "")
        self.assertEqual(state.context_summary, "")
        self.assertEqual(state.context_action, "continue")
        self.assertEqual(state.raw_transcripts, [])
        self.assertEqual(state.discarded_turns, [])
        self.assertEqual(state.discarded_transcriptions, [])
        self.assertEqual(state.feedback, [])
        self.assertEqual(state.thoughts, [])

    def test_queue_depth_event_updates_state(self) -> None:
        state = PrototypeState()

        reduce_prototype_state(state, make_event("QueueDepthChanged", audio_turn_queue=2, raw_transcript_queue=1))

        self.assertEqual(state.queue_depths, {"audio_turn_queue": 2, "raw_transcript_queue": 1})


if __name__ == "__main__":
    unittest.main()

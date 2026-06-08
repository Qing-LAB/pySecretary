import unittest

from pysecretary.llm_queue import LLMRequest, LLMRequestQueue


def req(context_key: str, sequence: int, payload: str, depends_on: int | None = None) -> LLMRequest:
    return LLMRequest(context_key=context_key, sequence=sequence, payload=payload, depends_on=depends_on)


class LLMRequestQueueTests(unittest.TestCase):
    def test_pending_requests_coalesce_into_one_ordered_batch(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 2, "second"))
        q.submit(req("a", 1, "first"))
        q.submit(req("a", 3, "third"))

        self.assertEqual(q.pending_count("a"), 3)
        batch = q.begin("a")

        self.assertIsNotNone(batch)
        self.assertEqual([r.payload for r in batch], ["first", "second", "third"])
        self.assertEqual(q.pending_count("a"), 0)
        self.assertTrue(q.is_in_flight("a"))

    def test_unrelated_contexts_are_independent(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("client-a", 1, "a1"))
        q.submit(req("client-b", 1, "b1"))

        self.assertCountEqual(q.dispatchable_contexts(), ["client-a", "client-b"])
        batch_a = q.begin("client-a")

        # Claiming client-a leaves client-b untouched and still dispatchable.
        self.assertEqual([r.payload for r in batch_a], ["a1"])
        self.assertEqual(q.dispatchable_contexts(), ["client-b"])
        self.assertEqual(q.pending_count("client-b"), 1)

    def test_requests_accumulate_while_a_context_is_in_flight(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 1, "first"))
        q.begin("a")  # in flight

        q.submit(req("a", 2, "second"))
        q.submit(req("a", 3, "third"))
        # An in-flight context is not dispatchable and cannot be claimed again.
        self.assertEqual(q.dispatchable_contexts(), [])
        self.assertIsNone(q.begin("a"))

        q.complete("a")
        # After completion the accumulated requests coalesce into the next batch.
        batch = q.begin("a")
        self.assertEqual([r.payload for r in batch], ["second", "third"])

    def test_begin_bounds_batch_with_max_items(self) -> None:
        q = LLMRequestQueue()
        for i in range(5):
            q.submit(req("a", i, f"s{i}"))

        batch = q.begin("a", max_items=2)
        self.assertEqual([r.payload for r in batch], ["s0", "s1"])
        self.assertEqual(q.pending_count("a"), 3)  # remainder stays pending

        q.complete("a")
        batch2 = q.begin("a", max_items=2)
        self.assertEqual([r.payload for r in batch2], ["s2", "s3"])

    def test_complete_carries_state_for_next_batch(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 1, "first"))
        q.begin("a")
        q.complete("a", state={"transcript": "First."})

        self.assertEqual(q.get_state("a"), {"transcript": "First."})

    def test_peek_returns_earliest_pending_without_claiming(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 5, "later"))
        q.submit(req("a", 2, "earlier"))

        peeked = q.peek("a")
        self.assertEqual(peeked.payload, "earlier")
        self.assertEqual(q.pending_count("a"), 2)  # not claimed

    def test_process_available_dispatches_one_batch_per_context(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 1, "a1"))
        q.submit(req("a", 2, "a2"))
        q.submit(req("b", 1, "b1"))
        calls: list[tuple[str, list[str]]] = []

        def handler(context_key, batch, state):
            calls.append((context_key, [r.payload for r in batch]))
            return f"state-{context_key}"

        dispatched = q.process_available(handler)

        self.assertEqual(dispatched, 2)
        self.assertCountEqual(calls, [("a", ["a1", "a2"]), ("b", ["b1"])])
        self.assertEqual(q.get_state("a"), "state-a")
        self.assertFalse(q.is_in_flight("a"))
        self.assertEqual(q.pending_count(), 0)

    def test_process_available_respects_can_dispatch_gate(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 1, "a1"))
        q.submit(req("b", 1, "b1"))
        handled: list[str] = []

        q.process_available(
            lambda key, batch, state: handled.append(key),
            can_dispatch=lambda key: key == "b",
        )

        self.assertEqual(handled, ["b"])
        # "a" was gated out and remains pending and claimable.
        self.assertEqual(q.pending_count("a"), 1)
        self.assertFalse(q.is_in_flight("a"))

    def test_process_available_releases_slot_even_if_handler_raises(self) -> None:
        q = LLMRequestQueue()
        q.submit(req("a", 1, "a1"))

        def boom(key, batch, state):
            raise RuntimeError("handler failed")

        with self.assertRaises(RuntimeError):
            q.process_available(boom)

        self.assertFalse(q.is_in_flight("a"))


if __name__ == "__main__":
    unittest.main()

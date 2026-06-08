# Transcription validation

A shared place to compare what you read against what the pipeline produced, so we can
evaluate STT/cleanup quality together.

## How to run a session

```bash
cd /home/qqing/Work/pySecretary
export PSEC_PROTOTYPE_LOG_PATH=/home/qqing/Work/pySecretary/validation/run1.log
export PSEC_PROTOTYPE_TRACE_LOG_PATH=/home/qqing/Work/pySecretary/validation/run1.trace.jsonl
scripts/run-prototype-ui.sh
```

Then open the dashboard, make sure KoboldCPP is up, click **Start**, and read
[`passage.txt`](passage.txt) aloud. Click **Stop** when done.

Two files are produced (both readable by me):
- `validation/run1.log` — the full cleaned transcript (overwritten each update, final state).
- `validation/run1.trace.jsonl` — an **append-only, time-ordered trace**: each `stt` event
  (raw Whisper text vs. cleaned), and each `merge` event (deduped sections in, editable tail,
  the LLM region out, the action, and the result). This lets me see whether a problem came
  from STT or from the LLM cleanup.

Tell me when you've finished a read and I'll read both and compare against the passage.

Use a fresh file per run if you want to keep history: `…/validation/run2.log`, etc.
(`*.log` is gitignored, so these stay local.)

## What I'll check against the passage

- **Coverage** — is any sentence missing or truncated (especially the long middle one)?
- **Names/terms** — "Eleanor Whitfield", "version two point six".
- **Numbers/dates** — "forty two thousand five hundred dollars" / "$42,500",
  "March third", "nine fifteen".
- **Homophones in context** — "their feedback is due there".
- **Cleanup quality** — grammar, run-ons, filler removal, no hallucinated sound cues.
- **Seams** — does the long sentence stay coherent across the 10s partial-flush boundary?

## Knobs to try between runs (longer audio → better Whisper accuracy)

```bash
export PSEC_PARTIAL_TURN_SECONDS=10      # force-flush after this long mid-speech
export PSEC_SILENCE_GAP_SECONDS=1.0      # a gap longer than this ends a turn
export PSEC_PARTIAL_OVERLAP_MIN_GAP_SECONDS=0.3   # overlap re-starts from a pause this long
export PSEC_PARTIAL_OVERLAP_MAX_SECONDS=2.0       # cap on the overlap window
```

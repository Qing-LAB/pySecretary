const state = {
  running: false,
  status: "stopped",
  raw_transcripts: [],
  smoothed_text: "",
  context_summary: "",
  context_action: "continue",
  feedback: [],
  thoughts: [],
  errors: [],
  events: [],
  last_audio_level: 0,
  audio_detected: false,
  in_speech_turn: false,
  queue_depths: { audio_turn_queue: 0, raw_transcript_queue: 0 },
  worker_options: {},
};

const OPTION_INPUTS = {
  energy_threshold: "opt-energy",
  transcription_min_peak_level: "opt-peak",
  silence_gap_seconds: "opt-silence",
  min_speech_seconds: "opt-minspeech",
  max_turn_seconds: "opt-maxturn",
};

const nodes = {
  status: document.getElementById("status"),
  audioState: document.getElementById("audio-state"),
  queueDepth: document.getElementById("queue-depth"),
  start: document.getElementById("start-button"),
  stop: document.getElementById("stop-button"),
  clear: document.getElementById("clear-button"),
  meter: document.getElementById("audio-meter"),
  transcript: document.getElementById("transcript"),
  raw: document.getElementById("raw-transcript"),
  latestFeedback: document.getElementById("latest-feedback"),
  latestThought: document.getElementById("latest-thought"),
  errors: document.getElementById("errors"),
  events: document.getElementById("events"),
};

// Previously rendered transcript, so each update can reveal only the changed tail.
let prevTranscript = "";

function applySnapshot(snapshot) {
  Object.assign(state, snapshot);
  prevTranscript = state.smoothed_text || "";
  render();
}

function applyEvent(event) {
  state.events.push(event);
  state.events = state.events.slice(-200);
  const payload = event.payload || {};

  if (event.type === "AssistantStateChanged") {
    state.status = payload.status || state.status;
    state.running = !["stopped", "idle", "error"].includes(state.status);
  } else if (event.type === "RecordingStarted") {
    state.running = true;
    state.status = "listening";
  } else if (event.type === "RecordingStopped") {
    state.running = false;
    state.status = "stopped";
  } else if (event.type === "AudioLevelChanged") {
    state.last_audio_level = Number(payload.level || 0);
    state.audio_detected = Boolean(payload.speech_detected);
    state.in_speech_turn = Boolean(payload.in_speech_turn);
  } else if (event.type === "QueueDepthChanged") {
    state.queue_depths = {
      audio_turn_queue: Number(payload.audio_turn_queue || 0),
      raw_transcript_queue: Number(payload.raw_transcript_queue || 0),
    };
  } else if (event.type === "WorkerOptionsChanged") {
    state.worker_options = payload.options || {};
  } else if (event.type === "RawTranscriptReceived") {
    state.raw_transcripts.push({
      sequence: Number(payload.sequence || 0),
      text: payload.text || "",
    });
    state.raw_transcripts = state.raw_transcripts.slice(-50);
  } else if (event.type === "SmoothedTranscriptUpdated") {
    state.smoothed_text = payload.text || "";
    state.context_action = payload.context_action || state.context_action;
    if (payload.context_summary || payload.context_action === "renew") {
      state.context_summary = payload.context_summary || "";
    }
  } else if (event.type === "MergeFeedbackReceived") {
    state.feedback.push(payload.text || "");
    state.feedback = state.feedback.slice(-50);
  } else if (event.type === "ThoughtCaptured") {
    state.thoughts.push(payload.text || "");
    state.thoughts = state.thoughts.slice(-50);
  } else if (event.type === "AssistantError") {
    state.errors.push(`${payload.stage || "error"}: ${payload.message || ""}`);
    state.status = "error";
    state.running = false;
  } else if (event.type === "PrototypeTranscriptCleared") {
    state.raw_transcripts = [];
    state.smoothed_text = "";
    state.context_summary = "";
    state.context_action = "continue";
    state.feedback = [];
    state.thoughts = [];
    state.errors = [];
  }

  render();
}

function render() {
  nodes.status.textContent = state.status;
  nodes.status.dataset.running = String(state.running);
  nodes.audioState.textContent = `audio: ${state.audio_detected ? "detected" : "quiet"} ${(state.last_audio_level || 0).toFixed(3)}${state.in_speech_turn ? " (turn)" : ""}`;
  nodes.audioState.dataset.detected = String(state.audio_detected);
  nodes.queueDepth.textContent = `queues ${state.queue_depths.audio_turn_queue || 0} / ${state.queue_depths.raw_transcript_queue || 0}`;
  nodes.start.disabled = state.running;
  nodes.stop.disabled = !state.running;
  nodes.meter.style.width = `${Math.round(Math.min(1, state.last_audio_level || 0) * 100)}%`;

  renderTranscript();
  renderWorkerOptions();
  renderRaw();
  nodes.latestFeedback.textContent = state.feedback[state.feedback.length - 1] || "";
  nodes.latestThought.textContent = state.thoughts[state.thoughts.length - 1] || "";
  renderStack(nodes.errors, state.errors.slice(-20));
  renderStack(nodes.events, state.events.slice(-30).map(formatEventLine));
}

function commonPrefixLength(a, b) {
  const max = Math.min(a.length, b.length);
  let i = 0;
  while (i < max && a[i] === b[i]) i += 1;
  return i;
}

// One growing transcript: unchanged text in normal color, the newly appended tail
// fades in (streaming feel), and a blinking cursor follows while capture runs.
function renderTranscript() {
  const text = state.smoothed_text || "";
  const wasNearBottom =
    nodes.transcript.scrollTop + nodes.transcript.clientHeight >= nodes.transcript.scrollHeight - 30;

  nodes.transcript.replaceChildren();
  const common = commonPrefixLength(prevTranscript, text);
  const stable = text.slice(0, common);
  const delta = text.slice(common);

  if (stable) {
    const span = document.createElement("span");
    span.textContent = stable;
    nodes.transcript.appendChild(span);
  }
  if (delta) {
    const span = document.createElement("span");
    span.className = "t-stream";
    span.textContent = delta;
    nodes.transcript.appendChild(span);
  }
  if (state.running) {
    const cursor = document.createElement("span");
    cursor.className = "t-cursor";
    cursor.textContent = "▍";
    nodes.transcript.appendChild(cursor);
  }
  if (!text) {
    nodes.transcript.textContent = state.running ? "Listening…" : "Press Start and begin speaking.";
  }

  prevTranscript = text;
  if (wasNearBottom) {
    nodes.transcript.scrollTop = nodes.transcript.scrollHeight;
  }
}

function renderWorkerOptions() {
  for (const [key, id] of Object.entries(OPTION_INPUTS)) {
    const input = document.getElementById(id);
    if (!input || input === document.activeElement) continue;
    const value = state.worker_options[key];
    if (value !== undefined && value !== null) input.value = value;
  }
}

function renderRaw() {
  nodes.raw.replaceChildren();
  for (const item of state.raw_transcripts.slice(-20)) {
    const div = document.createElement("div");
    div.className = "stack-item";
    const label = item.sequence ? `${item.sequence}. ` : "";
    div.textContent = `${label}${item.text || ""}`;
    nodes.raw.appendChild(div);
  }
}

function renderStack(node, items) {
  node.replaceChildren();
  for (const text of items) {
    const item = document.createElement("div");
    item.className = "stack-item";
    item.textContent = text;
    node.appendChild(item);
  }
}

function formatEventLine(event) {
  const p = event.payload || {};
  if (event.type === "TranscriptionDiscarded") return `discarded: ${p.reason || ""} ${p.text || ""}`.trim();
  if (event.type === "SpeechTurnDiscarded") return `turn dropped: ${p.reason || ""}`;
  if (event.type === "TranscriptMergeDeferred") return `merge waiting: ${p.reason || ""}`;
  if (event.type === "QueueDepthChanged") return `queues ${p.audio_turn_queue || 0}/${p.raw_transcript_queue || 0}`;
  return event.type;
}

async function sendCommand(type, payload = {}) {
  await fetch("/api/commands", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, payload }),
  });
}

nodes.start.addEventListener("click", () => sendCommand("StartAutomaticCapture"));
nodes.stop.addEventListener("click", () => sendCommand("StopAutomaticCapture"));
nodes.clear.addEventListener("click", () => sendCommand("ClearPrototypeTranscript"));

const optionsForm = document.getElementById("options-form");
if (optionsForm) {
  optionsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const options = {};
    for (const [key, id] of Object.entries(OPTION_INPUTS)) {
      const input = document.getElementById(id);
      if (input && input.value !== "") options[key] = Number(input.value);
    }
    sendCommand("UpdateWorkerOption", { options });
  });
}

fetch("/api/state")
  .then((response) => response.json())
  .then(applySnapshot);

const events = new EventSource("/api/events");
events.addEventListener("snapshot", (message) => applySnapshot(JSON.parse(message.data)));
events.addEventListener("event", (message) => applyEvent(JSON.parse(message.data)));

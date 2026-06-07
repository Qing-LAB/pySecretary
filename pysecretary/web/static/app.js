const state = {
  running: false,
  status: "stopped",
  raw_transcripts: [],
  discarded_turns: [],
  discarded_transcriptions: [],
  smoothed_text: "",
  committed_text: "",
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
  selected_turn_id: "",
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
  smoothed: document.getElementById("smoothed-output"),
  fullTranscript: document.getElementById("full-transcript"),
  raw: document.getElementById("raw-transcript"),
  latestFeedback: document.getElementById("latest-feedback"),
  latestThought: document.getElementById("latest-thought"),
  selectedTurn: document.getElementById("selected-turn"),
  selectedFeedback: document.getElementById("selected-feedback"),
  selectedThoughts: document.getElementById("selected-thoughts"),
  errors: document.getElementById("errors"),
  events: document.getElementById("events"),
};

// Tracks the previously rendered active-context text so each update can reveal only
// the newly changed tail with a streaming-style highlight.
let prevActiveText = "";

function applySnapshot(snapshot) {
  Object.assign(state, snapshot);
  ensureSelectedTurn();
  // Avoid animating the whole transcript when a fresh snapshot loads.
  prevActiveText = state.smoothed_text || "";
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
  } else if (event.type === "SpeechTurnDiscarded") {
    state.discarded_turns.push({
      turn_id: payload.turn_id || "",
      reason: payload.reason || "",
      peak_level: Number(payload.peak_level || 0),
    });
  } else if (event.type === "RawTranscriptReceived") {
    state.raw_transcripts.push({
      turn_id: payload.turn_id || "",
      sequence: Number(payload.sequence || 0),
      text: payload.text || "",
      captured_at: Number(payload.captured_at || 0),
      transcribed_at: Number(payload.transcribed_at || 0),
      duration_seconds: Number(payload.duration_seconds || 0),
      speech_seconds: Number(payload.speech_seconds || 0),
      peak_level: Number(payload.peak_level || 0),
    });
    state.selected_turn_id = payload.turn_id || state.selected_turn_id;
  } else if (event.type === "TranscriptionDiscarded") {
    state.discarded_transcriptions.push({
      turn_id: payload.turn_id || "",
      text: payload.text || "",
      reason: payload.reason || "",
    });
  } else if (event.type === "SmoothedTranscriptUpdated") {
    state.smoothed_text = payload.text || "";
    if ("committed_text" in payload) {
      state.committed_text = payload.committed_text || "";
    }
    if (payload.context_summary || payload.context_action === "renew") {
      state.context_summary = payload.context_summary || "";
    }
    state.context_action = payload.context_action || state.context_action;
  } else if (event.type === "MergeFeedbackReceived") {
    state.feedback.push({ turn_id: payload.turn_id || "", text: payload.text || "" });
  } else if (event.type === "ThoughtCaptured") {
    state.thoughts.push({ turn_id: payload.turn_id || "", text: payload.text || "" });
  } else if (event.type === "AssistantError") {
    state.errors.push({ stage: payload.stage || "", message: payload.message || "" });
    state.status = "error";
    state.running = false;
  } else if (event.type === "PrototypeTranscriptCleared") {
    state.raw_transcripts = [];
    state.discarded_turns = [];
    state.discarded_transcriptions = [];
    state.smoothed_text = "";
    state.committed_text = "";
    state.context_summary = "";
    state.context_action = "continue";
    state.feedback = [];
    state.thoughts = [];
    state.errors = [];
    state.last_audio_level = 0;
    state.audio_detected = false;
    state.in_speech_turn = false;
    state.queue_depths = { audio_turn_queue: 0, raw_transcript_queue: 0 };
    state.selected_turn_id = "";
  }

  render();
}

function render() {
  nodes.status.textContent = state.status;
  nodes.status.dataset.running = String(state.running);
  nodes.audioState.textContent = `audio: ${state.audio_detected ? "detected" : "quiet"} level ${(state.last_audio_level || 0).toFixed(3)} ${state.in_speech_turn ? "turn" : ""}`.trim();
  nodes.audioState.dataset.detected = String(state.audio_detected);
  nodes.queueDepth.textContent = `queues: audio ${state.queue_depths.audio_turn_queue || 0} / text ${state.queue_depths.raw_transcript_queue || 0}`;
  nodes.start.disabled = state.running;
  nodes.stop.disabled = !state.running;
  nodes.meter.style.width = `${Math.round(Math.min(1, state.last_audio_level || 0) * 100)}%`;
  const active = state.smoothed_text || "";
  const settled = state.committed_text || "";
  // Main panel: only the active context, streamed in with a live cursor.
  renderTranscript(nodes.smoothed, "", active, prevActiveText, state.running);
  // Full panel: settled history (muted) + active context (accent), scrollable.
  if (nodes.fullTranscript) {
    renderTranscript(nodes.fullTranscript, settled, active, prevActiveText, state.running);
  }
  prevActiveText = active;
  renderRawTranscripts();
  renderWorkerOptions();
  renderLatest();
  renderSelectedTurn();
  renderStack(nodes.errors, state.errors.map((item) => `${item.stage || "error"}: ${item.message || ""}`));
  renderStack(nodes.events, state.events.slice(-30).map(formatEventLine));
}

function commonPrefixLength(a, b) {
  const max = Math.min(a.length, b.length);
  let i = 0;
  while (i < max && a[i] === b[i]) {
    i += 1;
  }
  return i;
}

// Renders settled (committed) text in a muted color and the active context in an accent
// color. The portion of the active text that changed since the last render fades in, and
// a blinking cursor follows it while capture is running, giving a streaming feel.
function renderTranscript(node, settledText, activeText, previousActive, running) {
  if (!node) {
    return;
  }
  node.replaceChildren();

  if (settledText && settledText.trim()) {
    const settled = document.createElement("span");
    settled.className = "t-settled";
    settled.textContent = settledText.endsWith("\n") ? settledText : `${settledText}\n\n`;
    node.appendChild(settled);
  }

  // Only treat the tail as "new" when the active text grew from the same prefix;
  // a context renew or revision resets and re-reveals the whole active block.
  const common = commonPrefixLength(previousActive || "", activeText);
  const stable = activeText.slice(0, common);
  const delta = activeText.slice(common);

  if (stable) {
    const span = document.createElement("span");
    span.className = "t-active";
    span.textContent = stable;
    node.appendChild(span);
  }
  if (delta) {
    const span = document.createElement("span");
    span.className = "t-active t-stream";
    span.textContent = delta;
    node.appendChild(span);
  }
  if (running) {
    const cursor = document.createElement("span");
    cursor.className = "t-cursor";
    cursor.textContent = "▍";
    node.appendChild(cursor);
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

function renderRawTranscripts() {
  nodes.raw.replaceChildren();
  for (const item of state.raw_transcripts) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "stack-item raw-item";
    if (item.turn_id === state.selected_turn_id) {
      button.classList.add("selected");
    }
    const sectionLabel = item.sequence ? `${item.sequence}. ` : "";
    button.textContent = `${sectionLabel}${item.text || ""}`;
    button.addEventListener("click", () => {
      state.selected_turn_id = item.turn_id || "";
      render();
    });
    nodes.raw.appendChild(button);
  }
}

function renderWorkerOptions() {
  for (const [key, id] of Object.entries(OPTION_INPUTS)) {
    const input = document.getElementById(id);
    if (!input || input === document.activeElement) {
      continue;
    }
    const value = state.worker_options[key];
    if (value !== undefined && value !== null) {
      input.value = value;
    }
  }
}

function renderLatest() {
  const latestFeedback = state.feedback[state.feedback.length - 1];
  const latestThought = state.thoughts[state.thoughts.length - 1];
  nodes.latestFeedback.textContent = latestFeedback ? latestFeedback.text : "";
  nodes.latestThought.textContent = latestThought ? latestThought.text : "";
}

function renderSelectedTurn() {
  const turnId = state.selected_turn_id || "";
  const raw = state.raw_transcripts.find((item) => item.turn_id === turnId);
  nodes.selectedTurn.textContent = raw ? `${raw.sequence ? `section ${raw.sequence}: ` : ""}${raw.text}` : "";
  renderStack(nodes.selectedFeedback, state.feedback.filter((item) => item.turn_id === turnId).map((item) => item.text));
  renderStack(nodes.selectedThoughts, state.thoughts.filter((item) => item.turn_id === turnId).map((item) => item.text));
}

function ensureSelectedTurn() {
  if (state.selected_turn_id) {
    return;
  }
  const latestRaw = state.raw_transcripts[state.raw_transcripts.length - 1];
  state.selected_turn_id = latestRaw ? latestRaw.turn_id || "" : "";
}

function formatEventLine(event) {
  const payload = event.payload || {};
  if (event.type === "SpeechTurnDiscarded") {
    return `${event.type}: ${payload.reason || ""} peak=${Number(payload.peak_level || 0).toFixed(3)}`;
  }
  if (event.type === "TranscriptMergeDeferred") {
    return `${event.type}: ${payload.reason || ""}`;
  }
  if (event.type === "TranscriptionDiscarded") {
    return `${event.type}: ${payload.reason || ""} ${payload.text || ""}`.trim();
  }
  if (event.type === "QueueDepthChanged") {
    return `${event.type}: audio=${payload.audio_turn_queue || 0} text=${payload.raw_transcript_queue || 0}`;
  }
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
      if (input && input.value !== "") {
        options[key] = Number(input.value);
      }
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

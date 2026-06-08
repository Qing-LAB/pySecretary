# KoboldCPP Deployment For pySecretary

This document defines how KoboldCPP should be deployed so it matches the `pysecretary.koboldcpp` adapter design. Use it before changing pySecretary code: if KoboldCPP does not match this runtime contract, fix deployment first or update the adapter design and tests together.

## Target Runtime

pySecretary expects one local KoboldCPP server that provides:

- LLM chat completions.
- Whisper speech-to-text transcription.
- Text-to-speech WAV generation.
- API documentation at `/api`.
- Version/capability metadata at `/api/extra/version`.

Default base URL:

```bash
http://localhost:5001
```

The adapter prefers OpenAI-compatible routes and falls back to native KoboldCPP routes:

| Capability | Preferred Route | Fallback Route |
| --- | --- | --- |
| LLM | `/v1/chat/completions` | `/api/v1/generate` |
| STT | `/v1/audio/transcriptions` | `/api/extra/transcribe` |
| TTS | `/v1/audio/speech` | `/api/extra/tts` |

## Required KoboldCPP Capabilities

`GET /api/extra/version` should report:

```json
{
  "llm": true,
  "transcribe": true,
  "tts": true
}
```

Other fields may vary. For the current project setup, we have observed:

```json
{
  "result": "KoboldCpp",
  "version": "1.113.2",
  "protected": false,
  "llm": true,
  "transcribe": true,
  "tts": true
}
```

## KoboldCPP Launch Checklist

Use either the GUI launcher or command-line flags. KoboldCPP's official docs recommend checking the current binary's `--help` output because flags can change between versions.

Minimum launch requirements:

- Load a GGUF/GGML text model.
- Bind the server to port `5001`, or update `PSEC_API_BASE`.
- Load a Whisper model for STT.
- Load a TTS model.
- For Qwen3TTS or OuteTTS, also load the matching wav tokenizer.
- If using authentication, set pySecretary's `PSEC_API_KEY` to the same token/password expected by KoboldCPP.

## Known Local Deployment

Current local KoboldCPP directory:

```text
koboldcpp/
├── koboldcpp
├── models
│   ├── Kokoro_no_espeak_Q4.gguf
│   ├── Qwen_Qwen3.5-9B-Q4_K_M.gguf
│   └── whisper-small-q5_1.bin
└── start-chat-model.sh
```

The pySecretary-compatible launch uses:

- LLM: `Qwen_Qwen3.5-9B-Q4_K_M.gguf`
- STT: `whisper-small-q5_1.bin`
- TTS: `Kokoro_no_espeak_Q4.gguf`
- Port: `5001`
- Host: `127.0.0.1`
- CUDA with `22` GPU layers
- Context size `16384`
- Flash attention and smart context enabled

### Model sources

These are where the example models come from. Filenames are the local copies; download the
GGUF/GGML files and point the launch flags at them.

| Role | Example file | Source |
| --- | --- | --- |
| LLM | `Qwen_Qwen3.5-9B-Q4_K_M.gguf` | Qwen GGUF builds on Hugging Face, e.g. [`unsloth/Qwen3.5-9B-GGUF`](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF) (pick the `Q4_K_M` file); official Qwen GGUF repos live under the [Qwen org](https://huggingface.co/Qwen). |
| STT (Whisper) | `whisper-small-q5_1.bin` | Official whisper.cpp GGML models: [`ggerganov/whisper.cpp`](https://huggingface.co/ggerganov/whisper.cpp/tree/main) (list + sizes in the [whisper.cpp models README](https://github.com/ggml-org/whisper.cpp/tree/main/models)). |
| TTS | `Kokoro_no_espeak_Q4.gguf` | Official KoboldCpp TTS repo: [`koboldcpp/tts`](https://huggingface.co/koboldcpp/tts) (alt: [`mmwillet2/Kokoro_GGUF`](https://huggingface.co/mmwillet2/Kokoro_GGUF)). |

### Whisper accuracy and VRAM

In KoboldCpp, Whisper has **no GPU offload** — it runs on CPU (only the LLM via `--gpulayers`
and TTS via `--ttsgpu` use the GPU). So a larger, more accurate Whisper model costs RAM/CPU,
not VRAM, and will not compete with the LLM on the GPU.

For much better word accuracy than `whisper-small` at low CPU cost, prefer
[`ggml-large-v3-turbo-q5_0.bin`](https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q5_0.bin)
(~547 MiB — near `large-v3` accuracy, much faster on CPU). `medium-q5_0` is a smaller step up;
`large-v3-q5_0` (~1.1 GiB) is the most accurate but slower on CPU. Swap by changing only the
`--whispermodel` flag.

Current script:

```bash
#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$BASE_DIR/models"
BINARY="./koboldcpp"

"$BINARY" \
  --model "$MODEL_DIR/Qwen_Qwen3.5-9B-Q4_K_M.gguf" \
  --usecuda \
  --gpulayers 22 \
  --contextsize 16384 \
  --flashattention \
  --smartcontext \
  --whispermodel "$MODEL_DIR/whisper-small-q5_1.bin" \
  --ttsmodel "$MODEL_DIR/Kokoro_no_espeak_Q4.gguf" \
  --port 5001 \
  --host 127.0.0.1
```

Recommended path-safe version:

```bash
#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
MODEL_DIR="$BASE_DIR/models"
BINARY="$BASE_DIR/koboldcpp"

"$BINARY" \
  --model "$MODEL_DIR/Qwen_Qwen3.5-9B-Q4_K_M.gguf" \
  --usecuda \
  --gpulayers 22 \
  --contextsize 16384 \
  --flashattention \
  --smartcontext \
  --whispermodel "$MODEL_DIR/whisper-small-q5_1.bin" \
  --ttsmodel "$MODEL_DIR/Kokoro_no_espeak_Q4.gguf" \
  --port 5001 \
  --host 127.0.0.1
```

The only behavioral difference is `BINARY="$BASE_DIR/koboldcpp"`. That lets the script work even when launched from another directory.

Because the server binds to `127.0.0.1`, either of these pySecretary base URLs should work:

```bash
export PSEC_API_BASE="http://127.0.0.1:5001"
export PSEC_API_BASE="http://localhost:5001"
```

Prefer `http://127.0.0.1:5001` if `localhost` resolves to IPv6 first on a given machine.

Example Linux shape:

```bash
./koboldcpp \
  --model /path/to/llm.gguf \
  --port 5001 \
  --whispermodel /path/to/whisper.bin \
  --ttsmodel /path/to/tts.gguf
```

Example with TTS wav tokenizer:

```bash
./koboldcpp \
  --model /path/to/llm.gguf \
  --port 5001 \
  --whispermodel /path/to/whisper.bin \
  --ttsmodel /path/to/tts.gguf \
  --ttswavtokenizer /path/to/wavtokenizer.gguf
```

Optional TTS-related flags that may be useful:

- `--ttsgpu`: run supported TTS models on GPU.
- `--ttsthreads`: set TTS thread count.
- `--ttsmaxlen`: limit maximum generated audio length.
- `--ttsdir`: provide voice-cloning sample WAV files for supported Qwen3TTS models.

## pySecretary Environment

Recommended defaults:

```bash
export PSEC_API_BASE="http://localhost:5001"
export PSEC_STT_MODEL="kcpp"
export PSEC_LLM_MODEL="kcpp"
export PSEC_TTS_MODEL="kcpp"
export PSEC_TTS_VOICE="alloy"
```

If KoboldCPP is protected:

```bash
export PSEC_API_KEY="your-koboldcpp-token-or-password"
```

## Validation

Run these checks after launching KoboldCPP.

### 1. pySecretary Discovery

```bash
python -m pysecretary inspect-kobold
```

Expected healthy shape:

```json
{
  "api_base": "http://localhost:5001",
  "version": "1.113.2",
  "model_id": "koboldcpp/...",
  "capabilities": {
    "llm": true,
    "transcribe": true,
    "tts": true
  },
  "llm": {
    "style": "openai",
    "endpoint": "/v1/chat/completions"
  },
  "stt": {
    "style": "openai",
    "endpoint": "/v1/audio/transcriptions"
  },
  "tts": {
    "style": "openai",
    "endpoint": "/v1/audio/speech"
  }
}
```

Native fallback endpoints are acceptable, but if a capability is `unavailable`, the pySecretary module contract is not satisfied.

### 2. Capability Metadata

```bash
curl -sS -m 5 -i http://localhost:5001/api/extra/version
```

Look for:

- HTTP `200`.
- `"llm": true`.
- `"transcribe": true`.
- `"tts": true`.

### 3. Model Metadata

```bash
curl -sS -m 5 -i http://localhost:5001/v1/models
```

Expected:

- HTTP `200`.
- JSON `data` list with at least one model id.

### 4. Chat Endpoint

```bash
curl -sS -m 5 -i \
  -H 'Content-Type: application/json' \
  -d '{"model":"kcpp","messages":[{"role":"user","content":"Reply with OK only."}],"max_tokens":16,"temperature":0}' \
  http://localhost:5001/v1/chat/completions
```

Expected:

- HTTP `200`.
- JSON `choices`.
- Assistant content in `choices[0].message.content`.

Note: reasoning models may emit `<think>` content. The adapter exposes the raw server response; later pySecretary modules must sanitize thought traces before TTS.

### 5. TTS Endpoint

```bash
curl -sS -m 5 -i \
  -o /tmp/pysecretary-kcpp-tts.wav \
  -H 'Content-Type: application/json' \
  -d '{"model":"kcpp","input":"KoboldCPP speech test.","voice":"alloy"}' \
  http://localhost:5001/v1/audio/speech
```

Expected:

- HTTP `200`.
- `Content-Type` beginning with `audio/`.
- WAV bytes written to `/tmp/pysecretary-kcpp-tts.wav`.

### 6. STT Endpoint

Use a 16-bit WAV file, preferably 16 kHz mono:

```bash
curl -sS -m 5 -i \
  -X POST \
  -F model=kcpp \
  -F 'file=@/path/to/test.wav;type=audio/wav' \
  http://localhost:5001/v1/audio/transcriptions
```

Expected:

- HTTP `200`.
- JSON with `text`.

Silence may return an empty string, which is still a valid response shape.

## Troubleshooting

### `transcribe` is false

KoboldCPP did not load a Whisper model. Relaunch with a Whisper model in the GUI Audio tab or with the appropriate command-line flag, then rerun:

```bash
python -m pysecretary inspect-kobold
```

### `tts` is false

KoboldCPP did not load a TTS model. Load a supported TTS model. For Qwen3TTS and OuteTTS, also load the wav tokenizer.

### `llm` is false

KoboldCPP did not initialize text generation. Load a GGUF/GGML text model.

### Endpoint is missing but capability is true

Check the live API docs:

Open `http://localhost:5001/api` in a browser.

or inspect manually:

```bash
curl -sS -m 5 -i http://localhost:5001/api
```

If route names changed in a newer KoboldCPP release, update:

- `docs/modules/koboldcpp.md`
- `pysecretary/koboldcpp.py`
- `tests/test_koboldcpp.py`

### Protected server rejects requests

Set:

```bash
export PSEC_API_KEY="your-koboldcpp-token-or-password"
```

Then rerun `python -m pysecretary inspect-kobold`.

### Chat works but TTS speaks model thoughts

This is not a deployment failure. It means the downstream LLM output sanitizer is not implemented yet. The design requires `<think>...</think>` content to be separated before text reaches TTS.

## Sources

- KoboldCPP README: https://github.com/LostRuins/koboldcpp
- KoboldCPP wiki: https://github.com/LostRuins/koboldcpp/wiki
- Local KoboldCPP API docs: `http://localhost:5001/api`

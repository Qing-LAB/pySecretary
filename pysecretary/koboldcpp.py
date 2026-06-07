from __future__ import annotations

import base64
import re
from dataclasses import dataclass, field
from typing import Any, Literal

import requests


EndpointStyle = Literal["openai", "native", "unavailable"]


class KoboldCppError(RuntimeError):
    """Base error for KoboldCPP integration failures."""


class KoboldCppDiscoveryError(KoboldCppError):
    """Raised when the local KoboldCPP server cannot be profiled."""


@dataclass(frozen=True)
class KoboldCppProfile:
    api_base: str
    version: str | None = None
    model_id: str | None = None
    protected: bool = False
    capabilities: dict[str, bool] = field(default_factory=dict)
    routes: frozenset[str] = frozenset()
    llm_style: EndpointStyle = "unavailable"
    llm_endpoint: str = ""
    stt_style: EndpointStyle = "unavailable"
    stt_endpoint: str = ""
    tts_style: EndpointStyle = "unavailable"
    tts_endpoint: str = ""

    def endpoint_url(self, path: str) -> str:
        return f"{self.api_base.rstrip('/')}/{path.lstrip('/')}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_base": self.api_base,
            "version": self.version,
            "model_id": self.model_id,
            "protected": self.protected,
            "capabilities": dict(sorted(self.capabilities.items())),
            "routes": sorted(self.routes),
            "llm": {"style": self.llm_style, "endpoint": self.llm_endpoint},
            "stt": {"style": self.stt_style, "endpoint": self.stt_endpoint},
            "tts": {"style": self.tts_style, "endpoint": self.tts_endpoint},
        }


class KoboldCppDiscovery:
    def __init__(
        self,
        api_base: str,
        api_key: str | None = None,
        timeout: float = 5.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or None
        self.timeout = timeout
        self.session = session or requests.Session()

    def discover(self) -> KoboldCppProfile:
        version_payload = self._get_json("/api/extra/version", required=True)
        routes = self._fetch_api_routes()
        model_id = self._fetch_model_id()
        capabilities = self._extract_capabilities(version_payload)

        llm_style, llm_endpoint = self._select_endpoint(
            capability="llm",
            capabilities=capabilities,
            routes=routes,
            primary=("/v1/chat/completions", "openai"),
            fallback=("/api/v1/generate", "native"),
        )
        stt_style, stt_endpoint = self._select_endpoint(
            capability="transcribe",
            capabilities=capabilities,
            routes=routes,
            primary=("/v1/audio/transcriptions", "openai"),
            fallback=("/api/extra/transcribe", "native"),
        )
        tts_style, tts_endpoint = self._select_endpoint(
            capability="tts",
            capabilities=capabilities,
            routes=routes,
            primary=("/v1/audio/speech", "openai"),
            fallback=("/api/extra/tts", "native"),
        )

        return KoboldCppProfile(
            api_base=self.api_base,
            version=self._string_or_none(version_payload.get("version")),
            model_id=model_id,
            protected=bool(version_payload.get("protected", False)),
            capabilities=capabilities,
            routes=frozenset(routes),
            llm_style=llm_style,
            llm_endpoint=llm_endpoint,
            stt_style=stt_style,
            stt_endpoint=stt_endpoint,
            tts_style=tts_style,
            tts_endpoint=tts_endpoint,
        )

    def _select_endpoint(
        self,
        capability: str,
        capabilities: dict[str, bool],
        routes: set[str],
        primary: tuple[str, EndpointStyle],
        fallback: tuple[str, EndpointStyle],
    ) -> tuple[EndpointStyle, str]:
        primary_path, primary_style = primary
        fallback_path, fallback_style = fallback
        capability_enabled = capabilities.get(capability)

        if capability_enabled is False and not self._has_any_route(routes, primary_path, fallback_path):
            return "unavailable", ""

        if self._route_known(routes, primary_path):
            return primary_style, primary_path
        if self._route_known(routes, fallback_path):
            return fallback_style, fallback_path
        return "unavailable", ""

    def _fetch_model_id(self) -> str | None:
        models_payload = self._get_json("/v1/models", required=False)
        data = models_payload.get("data")
        if isinstance(data, list) and data:
            first_model = data[0]
            if isinstance(first_model, dict):
                return self._string_or_none(first_model.get("id"))

        model_payload = self._get_json("/api/v1/model", required=False)
        return self._string_or_none(model_payload.get("result"))

    def _fetch_api_routes(self) -> set[str]:
        routes: set[str] = set()
        for path in ("/openapi.json", "/swagger.json", "/api"):
            response = self._get(path, required=False)
            if response is None:
                continue

            parsed = self._json_from_response(response)
            paths = parsed.get("paths") if isinstance(parsed, dict) else None
            if isinstance(paths, dict):
                routes.update(str(route) for route in paths)

            routes.update(self._extract_routes_from_text(response.text))
            if routes:
                break
        return routes

    def _get_json(self, path: str, required: bool) -> dict[str, Any]:
        response = self._get(path, required=required)
        if response is None:
            return {}

        payload = self._json_from_response(response)
        if isinstance(payload, dict):
            return payload

        if required:
            raise KoboldCppDiscoveryError(f"KoboldCPP endpoint did not return JSON: {path}")
        return {}

    def _get(self, path: str, required: bool) -> requests.Response | None:
        try:
            response = self.session.get(
                self._url(path),
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if required:
                raise KoboldCppDiscoveryError(
                    f"Unable to reach KoboldCPP at {self._url(path)}"
                ) from exc
            return None

    def _headers(self, **extra: str) -> dict[str, str]:
        headers = dict(extra)
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.api_base}/{path.lstrip('/')}"

    @staticmethod
    def _extract_capabilities(payload: dict[str, Any]) -> dict[str, bool]:
        ignored = {"result", "version", "protected"}
        return {
            key: value
            for key, value in payload.items()
            if key not in ignored and isinstance(value, bool)
        }

    @staticmethod
    def _extract_routes_from_text(text: str) -> set[str]:
        pattern = re.compile(r'"(?P<path>/(?:api|v1|sdapi)[^"]+)"\s*:\s*\{')
        return {match.group("path") for match in pattern.finditer(text)}

    @staticmethod
    def _has_any_route(routes: set[str], *paths: str) -> bool:
        return bool(routes) and any(path in routes for path in paths)

    @staticmethod
    def _json_from_response(response: requests.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {}

    @staticmethod
    def _route_known(routes: set[str], path: str) -> bool:
        return not routes or path in routes

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)


class KoboldCppClient:
    def __init__(
        self,
        api_base: str,
        api_key: str | None = None,
        request_timeout: float = 120.0,
        discovery_timeout: float = 5.0,
        profile: KoboldCppProfile | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key or None
        self.request_timeout = request_timeout
        self.discovery_timeout = discovery_timeout
        self.session = session or requests.Session()
        self.profile = profile or self.discover()

    @classmethod
    def from_config(cls, config: Any) -> "KoboldCppClient":
        return cls(
            api_base=config.api_base,
            api_key=config.api_key,
            request_timeout=getattr(config, "request_timeout", 120.0),
            discovery_timeout=getattr(config, "discovery_timeout", 5.0),
        )

    def discover(self) -> KoboldCppProfile:
        return KoboldCppDiscovery(
            api_base=self.api_base,
            api_key=self.api_key,
            timeout=self.discovery_timeout,
            session=self.session,
        ).discover()

    def refresh_profile(self) -> KoboldCppProfile:
        self.profile = self.discover()
        return self.profile

    def health(self) -> dict[str, Any]:
        return {
            "reachable": True,
            "profile": self.profile.to_dict(),
        }

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str = "kcpp",
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        if self.profile.llm_style == "openai":
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if max_tokens is not None:
                payload["max_tokens"] = max_tokens
            payload.update(extra)
            response = self._post_json(self.profile.llm_endpoint, payload)
            return response.json()

        if self.profile.llm_style == "native":
            prompt = self._messages_to_prompt(messages)
            payload = {
                "prompt": prompt,
                "temperature": temperature,
                "max_length": max_tokens or extra.pop("max_length", 512),
                "quiet": True,
            }
            payload.update(extra)
            response = self._post_json(self.profile.llm_endpoint, payload)
            text = self._extract_native_generation_text(response.json())
            return self._openai_chat_shape(model=model, text=text)

        raise KoboldCppError("KoboldCPP LLM endpoint is unavailable.")

    def transcribe_wav(
        self,
        audio_bytes: bytes,
        model: str = "kcpp",
        prompt: str = "",
        language: str = "en",
        suppress_non_speech: bool = False,
    ) -> str:
        if self.profile.stt_style == "openai":
            files = {"file": ("recording.wav", audio_bytes, "audio/wav")}
            data = {
                "model": model,
                "prompt": prompt,
                "language": language,
            }
            response = self._post_files(self.profile.stt_endpoint, files=files, data=data)
            return self._extract_transcription_text(response.json())

        if self.profile.stt_style == "native":
            payload = {
                "audio_data": base64.b64encode(audio_bytes).decode("ascii"),
                "prompt": prompt,
                "langcode": language,
                "suppress_non_speech": suppress_non_speech,
            }
            response = self._post_json(self.profile.stt_endpoint, payload)
            return self._extract_transcription_text(response.json())

        raise KoboldCppError("KoboldCPP transcription endpoint is unavailable.")

    def synthesize_speech(
        self,
        text: str,
        model: str = "kcpp",
        voice: str = "alloy",
        instruction: str = "",
        speaker_json: str | None = None,
    ) -> bytes:
        if self.profile.tts_style == "openai":
            payload = {
                "model": model,
                "voice": voice,
                "input": text,
            }
            response = self._post_json(self.profile.tts_endpoint, payload, accept="audio/wav")
            return self._extract_audio_bytes(response)

        if self.profile.tts_style == "native":
            payload: dict[str, Any] = {
                "input": text,
                "voice": voice,
                "instruction": instruction,
            }
            if speaker_json:
                payload["speaker_json"] = speaker_json
            response = self._post_json(self.profile.tts_endpoint, payload, accept="audio/wav")
            return self._extract_audio_bytes(response)

        raise KoboldCppError("KoboldCPP TTS endpoint is unavailable.")

    def _post_json(
        self,
        path: str,
        payload: dict[str, Any],
        accept: str | None = None,
    ) -> requests.Response:
        headers = self._headers({"Content-Type": "application/json"})
        if accept:
            headers["Accept"] = accept
        response = self.session.post(
            self._url(path),
            headers=headers,
            json=payload,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        return response

    def _post_files(
        self,
        path: str,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, str],
    ) -> requests.Response:
        response = self.session.post(
            self._url(path),
            headers=self._headers(),
            files=files,
            data=data,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        return response

    def _headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        result = dict(headers or {})
        if self.api_key:
            result["Authorization"] = f"Bearer {self.api_key}"
        return result

    def _url(self, path: str) -> str:
        return f"{self.api_base}/{path.lstrip('/')}"

    @staticmethod
    def _extract_audio_bytes(response: requests.Response) -> bytes:
        if response.headers.get("Content-Type", "").startswith("audio"):
            return response.content

        payload = response.json()
        audio_value = payload.get("audio") or payload.get("data") or payload.get("result")
        if isinstance(audio_value, str):
            try:
                return base64.b64decode(audio_value, validate=True)
            except ValueError:
                return audio_value.encode("utf-8")

        raise KoboldCppError("Unexpected KoboldCPP TTS response format.")

    @staticmethod
    def _extract_native_generation_text(payload: dict[str, Any]) -> str:
        results = payload.get("results")
        if isinstance(results, list) and results:
            first_result = results[0]
            if isinstance(first_result, dict):
                return str(first_result.get("text") or "").strip()
        return str(payload.get("text") or payload.get("result") or "").strip()

    @staticmethod
    def _extract_transcription_text(payload: dict[str, Any]) -> str:
        return str(
            payload.get("text")
            or payload.get("transcription")
            or payload.get("result")
            or ""
        ).strip()

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, str]]) -> str:
        lines = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            lines.append(f"{role}: {content}")
        lines.append("assistant:")
        return "\n".join(lines)

    @staticmethod
    def _openai_chat_shape(model: str, text: str) -> dict[str, Any]:
        return {
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }

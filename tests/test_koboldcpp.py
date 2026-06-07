import base64
import unittest

from pysecretary.koboldcpp import (
    KoboldCppApi,
    KoboldCppClient,
    KoboldCppDiscovery,
    KoboldCppDiscoveryError,
    KoboldCppError,
    KoboldCppProfile,
)
from tests.fakes import NO_JSON, FakeResponse, FakeSession


class KoboldCppDiscoveryTests(unittest.TestCase):
    def test_client_satisfies_public_api_protocol(self) -> None:
        client = KoboldCppClient(
            "http://local:5001",
            profile=KoboldCppProfile(api_base="http://local:5001"),
            session=FakeSession(),
        )

        self.assertIsInstance(client, KoboldCppApi)

    def test_discover_prefers_openai_compatible_routes(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse(
                    {
                        "result": "KoboldCpp",
                        "version": "1.113.2",
                        "protected": False,
                        "llm": True,
                        "transcribe": True,
                        "tts": True,
                    }
                ),
                "/api": FakeResponse(
                    NO_JSON,
                    text=(
                        '"/v1/chat/completions": {'
                        '"/v1/audio/transcriptions": {'
                        '"/v1/audio/speech": {'
                        '"/api/v1/generate": {'
                        '"/api/extra/transcribe": {'
                        '"/api/extra/tts": {'
                    ),
                ),
                "/v1/models": FakeResponse(
                    {
                        "data": [
                            {
                                "id": "koboldcpp/Qwen_Qwen3.5-9B-Q4_K_M",
                                "context_length": 8192,
                            }
                        ]
                    }
                ),
                "/api/extra/true_max_context_length": FakeResponse({"result": 16384}),
            }
        )

        profile = KoboldCppDiscovery("http://local:5001/", session=session).discover()

        self.assertEqual(profile.api_base, "http://local:5001")
        self.assertEqual(profile.version, "1.113.2")
        self.assertEqual(profile.model_id, "koboldcpp/Qwen_Qwen3.5-9B-Q4_K_M")
        self.assertEqual(profile.context_limit_tokens, 16384)
        self.assertFalse(profile.protected)
        self.assertEqual(profile.llm_style, "openai")
        self.assertEqual(profile.llm_endpoint, "/v1/chat/completions")
        self.assertEqual(profile.stt_style, "openai")
        self.assertEqual(profile.stt_endpoint, "/v1/audio/transcriptions")
        self.assertEqual(profile.tts_style, "openai")
        self.assertEqual(profile.tts_endpoint, "/v1/audio/speech")
        self.assertNotIn("protected", profile.capabilities)

    def test_discover_falls_back_to_native_routes(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse(
                    {
                        "result": "KoboldCpp",
                        "version": "1.113.2",
                        "llm": True,
                        "transcribe": True,
                        "tts": True,
                    }
                ),
                "/openapi.json": FakeResponse(
                    {
                        "paths": {
                            "/api/v1/generate": {},
                            "/api/extra/transcribe": {},
                            "/api/extra/tts": {},
                        }
                    }
                ),
                "/v1/models": FakeResponse(status_code=404),
                "/api/v1/model": FakeResponse({"result": "native-model"}),
            }
        )

        profile = KoboldCppDiscovery("http://local:5001", session=session).discover()

        self.assertEqual(profile.model_id, "native-model")
        self.assertEqual(profile.llm_style, "native")
        self.assertEqual(profile.llm_endpoint, "/api/v1/generate")
        self.assertEqual(profile.stt_style, "native")
        self.assertEqual(profile.stt_endpoint, "/api/extra/transcribe")
        self.assertEqual(profile.tts_style, "native")
        self.assertEqual(profile.tts_endpoint, "/api/extra/tts")

    def test_discover_marks_disabled_capability_unavailable_without_matching_route(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse(
                    {
                        "result": "KoboldCpp",
                        "version": "1.113.2",
                        "llm": True,
                        "transcribe": False,
                        "tts": True,
                    }
                ),
                "/openapi.json": FakeResponse(
                    {
                        "paths": {
                            "/v1/chat/completions": {},
                            "/v1/audio/speech": {},
                        }
                    }
                ),
                "/v1/models": FakeResponse({"data": [{"id": "model"}]}),
            }
        )

        profile = KoboldCppDiscovery("http://local:5001", session=session).discover()

        self.assertEqual(profile.llm_style, "openai")
        self.assertEqual(profile.stt_style, "unavailable")
        self.assertEqual(profile.stt_endpoint, "")
        self.assertEqual(profile.tts_style, "openai")

    def test_discover_uses_openai_routes_optimistically_when_route_docs_are_missing(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse(
                    {
                        "result": "KoboldCpp",
                        "version": "1.113.2",
                        "llm": True,
                        "transcribe": True,
                        "tts": True,
                    }
                ),
                "/openapi.json": FakeResponse(status_code=404),
                "/swagger.json": FakeResponse(status_code=404),
                "/api": FakeResponse(status_code=404),
                "/v1/models": FakeResponse({"data": [{"id": "model"}]}),
            }
        )

        profile = KoboldCppDiscovery("http://local:5001", session=session).discover()

        self.assertEqual(profile.routes, frozenset())
        self.assertEqual(profile.llm_endpoint, "/v1/chat/completions")
        self.assertEqual(profile.stt_endpoint, "/v1/audio/transcriptions")
        self.assertEqual(profile.tts_endpoint, "/v1/audio/speech")

    def test_required_version_metadata_failure_raises_discovery_error(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse(status_code=503),
            }
        )

        with self.assertRaises(KoboldCppDiscoveryError):
            KoboldCppDiscovery("http://local:5001", session=session).discover()

    def test_profile_to_dict_is_stable_and_sorted(self) -> None:
        profile = KoboldCppProfile(
            api_base="http://local:5001",
            version="1",
            model_id="model",
            capabilities={"tts": True, "llm": True},
            routes=frozenset({"/z", "/a"}),
            llm_style="openai",
            llm_endpoint="/v1/chat/completions",
        )

        payload = profile.to_dict()

        self.assertEqual(payload["routes"], ["/a", "/z"])
        self.assertEqual(payload["capabilities"], {"llm": True, "tts": True})
        self.assertIn("context_limit_tokens", payload)
        self.assertEqual(profile.endpoint_url("/api"), "http://local:5001/api")

    def test_discovery_extracts_context_limit_from_nested_runtime_metadata(self) -> None:
        session = FakeSession(
            get_map={
                "/api/extra/version": FakeResponse({"version": "1", "llm": True}),
                "/openapi.json": FakeResponse(status_code=404),
                "/swagger.json": FakeResponse(status_code=404),
                "/api": FakeResponse(status_code=404),
                "/v1/models": FakeResponse({"data": [{"id": "model"}]}),
                "/api/extra/true_max_context_length": FakeResponse(status_code=404),
                "/api/v1/config": FakeResponse({"model": {"n_ctx": 12288}}),
            }
        )

        profile = KoboldCppDiscovery("http://local:5001", session=session).discover()

        self.assertEqual(profile.context_limit_tokens, 12288)


class KoboldCppClientTests(unittest.TestCase):
    def test_openai_chat_transcribe_and_tts_requests(self) -> None:
        profile = KoboldCppProfile(
            api_base="http://local:5001",
            llm_style="openai",
            llm_endpoint="/v1/chat/completions",
            stt_style="openai",
            stt_endpoint="/v1/audio/transcriptions",
            tts_style="openai",
            tts_endpoint="/v1/audio/speech",
        )
        session = FakeSession(
            post_map={
                "/v1/chat/completions": FakeResponse({"choices": [{"message": {"content": "ok"}}]}),
                "/v1/audio/transcriptions": FakeResponse({"text": "hello"}),
                "/v1/audio/speech": FakeResponse(
                    headers={"Content-Type": "audio/wav"},
                    content=b"audio",
                ),
            }
        )
        client = KoboldCppClient("http://local:5001", api_key="key", profile=profile, session=session)

        chat = client.chat_completion(
            [{"role": "user", "content": "hi"}],
            model="kcpp",
            temperature=0.1,
            max_tokens=12,
        )
        transcript = client.transcribe_wav(b"wav", model="stt", prompt="terms", language="en")
        audio = client.synthesize_speech("hello", model="tts", voice="voice-a")

        self.assertEqual(chat["choices"][0]["message"]["content"], "ok")
        self.assertEqual(transcript, "hello")
        self.assertEqual(audio, b"audio")
        self.assertEqual(session.post_calls[0]["path"], "/v1/chat/completions")
        self.assertEqual(session.post_calls[0]["json"]["max_tokens"], 12)
        self.assertEqual(session.post_calls[0]["headers"]["Authorization"], "Bearer key")
        self.assertEqual(session.post_calls[1]["path"], "/v1/audio/transcriptions")
        self.assertEqual(session.post_calls[1]["files"]["file"], ("recording.wav", b"wav", "audio/wav"))
        self.assertEqual(session.post_calls[1]["data"]["prompt"], "terms")
        self.assertEqual(session.post_calls[2]["path"], "/v1/audio/speech")
        self.assertEqual(session.post_calls[2]["headers"]["Accept"], "audio/wav")
        self.assertEqual(session.post_calls[2]["json"]["voice"], "voice-a")

    def test_native_chat_transcribe_and_tts_requests(self) -> None:
        profile = KoboldCppProfile(
            api_base="http://local:5001",
            llm_style="native",
            llm_endpoint="/api/v1/generate",
            stt_style="native",
            stt_endpoint="/api/extra/transcribe",
            tts_style="native",
            tts_endpoint="/api/extra/tts",
        )
        session = FakeSession(
            post_map={
                "/api/v1/generate": FakeResponse({"results": [{"text": "native answer"}]}),
                "/api/extra/transcribe": FakeResponse({"result": "native transcript"}),
                "/api/extra/tts": FakeResponse(
                    headers={"Content-Type": "audio/wav"},
                    content=b"native-audio",
                ),
            }
        )
        client = KoboldCppClient("http://local:5001", profile=profile, session=session)

        chat = client.chat_completion(
            [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
            max_tokens=7,
        )
        transcript = client.transcribe_wav(
            b"wav",
            prompt="terms",
            language="auto",
            suppress_non_speech=True,
        )
        audio = client.synthesize_speech(
            "hello",
            voice="kobo",
            instruction="calm",
            speaker_json='{"speaker": true}',
        )

        self.assertEqual(chat["choices"][0]["message"]["content"], "native answer")
        self.assertEqual(transcript, "native transcript")
        self.assertEqual(audio, b"native-audio")
        self.assertEqual(session.post_calls[0]["json"]["max_length"], 7)
        self.assertIn("system: be brief", session.post_calls[0]["json"]["prompt"])
        self.assertEqual(
            session.post_calls[1]["json"]["audio_data"],
            base64.b64encode(b"wav").decode("ascii"),
        )
        self.assertEqual(session.post_calls[1]["json"]["langcode"], "auto")
        self.assertTrue(session.post_calls[1]["json"]["suppress_non_speech"])
        self.assertEqual(session.post_calls[2]["json"]["voice"], "kobo")
        self.assertEqual(session.post_calls[2]["json"]["instruction"], "calm")
        self.assertEqual(session.post_calls[2]["json"]["speaker_json"], '{"speaker": true}')

    def test_unavailable_endpoints_raise_clear_errors(self) -> None:
        client = KoboldCppClient(
            "http://local:5001",
            profile=KoboldCppProfile(api_base="http://local:5001"),
            session=FakeSession(),
        )

        with self.assertRaises(KoboldCppError):
            client.chat_completion([])
        with self.assertRaises(KoboldCppError):
            client.transcribe_wav(b"wav")
        with self.assertRaises(KoboldCppError):
            client.synthesize_speech("text")

    def test_json_audio_payload_can_be_base64_decoded(self) -> None:
        profile = KoboldCppProfile(
            api_base="http://local:5001",
            tts_style="openai",
            tts_endpoint="/v1/audio/speech",
        )
        session = FakeSession(
            post_map={
                "/v1/audio/speech": FakeResponse(
                    {"audio": base64.b64encode(b"audio").decode("ascii")},
                    headers={"Content-Type": "application/json"},
                )
            }
        )
        client = KoboldCppClient("http://local:5001", profile=profile, session=session)

        self.assertEqual(client.synthesize_speech("hello"), b"audio")


if __name__ == "__main__":
    unittest.main()

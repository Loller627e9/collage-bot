"""Gemini client: JSON extraction, schema conversion, transports, fallback."""

from __future__ import annotations

import pytest

from pokego.gemini import (
    API_REVISION,
    DEFAULT_MODEL_FALLBACKS,
    GeminiClient,
    GeminiError,
    ImagePart,
    MissingApiKeyError,
    _first_text,
    _to_gemini_schema,
    extract_json,
)


class TestImagePart:
    def test_base64_roundtrip(self):
        part = ImagePart.from_bytes(b"hello", "image/png")
        assert part.to_base64() == "aGVsbG8="
        assert part.mime_type == "image/png"

    def test_from_path_reads_file(self, tmp_path):
        path = tmp_path / "shot.png"
        path.write_bytes(b"\x89PNG data")
        assert ImagePart.from_path(path).data == b"\x89PNG data"


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_without_language(self):
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_surrounding_prose(self):
        assert extract_json('Here you go:\n{"a": 1}\nHope that helps.') == {"a": 1}

    def test_empty_raises(self):
        with pytest.raises(GeminiError):
            extract_json("")

    def test_no_json_raises(self):
        with pytest.raises(GeminiError):
            extract_json("no json here at all")


class TestFirstText:
    def test_output_text(self):
        assert _first_text({"output_text": "hi"}) == "hi"

    def test_outputs_parts(self):
        payload = {"outputs": [{"content": [{"text": "a"}, {"text": "b"}]}]}
        assert _first_text(payload) == "ab"

    def test_generatecontent_candidates(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]}
        assert _first_text(payload) == "hi"

    def test_empty_payload(self):
        assert _first_text({}) == ""


class TestSchemaConversion:
    def test_preserves_nullable(self):
        """Gemini's Schema documents `nullable`, so it must survive conversion."""
        schema = {"type": "object", "properties": {
            "level": {"type": "integer", "nullable": True}}}
        assert _to_gemini_schema(schema)["properties"]["level"]["nullable"] is True

    def test_drops_unsupported_keys(self):
        schema = {"type": "object", "$schema": "x", "additionalProperties": False,
                  "properties": {"a": {"type": "string"}}}
        out = _to_gemini_schema(schema)
        assert "$schema" not in out
        assert "additionalProperties" not in out
        assert out["properties"]["a"] == {"type": "string"}

    def test_recurses_into_arrays(self):
        schema = {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "properties": {"a": {"type": "string"}}}}
        out = _to_gemini_schema(schema)
        assert "additionalProperties" not in out["items"]

    def test_keeps_enum_and_required(self):
        schema = {"type": "object", "required": ["a"],
                  "properties": {"a": {"type": "string", "enum": ["x", "y"]}}}
        out = _to_gemini_schema(schema)
        assert out["required"] == ["a"]
        assert out["properties"]["a"]["enum"] == ["x", "y"]


class TestModelFallbacks:
    def test_deprecated_model_is_not_first(self):
        assert DEFAULT_MODEL_FALLBACKS[0] == "gemini-3.8-flash"
        assert "gemini-2.5-flash" not in DEFAULT_MODEL_FALLBACKS[:3]

    def test_explicit_model_comes_first(self):
        client = GeminiClient("k", model="gemini-custom")
        assert client._models()[0] == "gemini-custom"

    def test_fallbacks_are_deduplicated(self):
        client = GeminiClient("k", model="gemini-3.8-flash")
        assert len(client._models()) == len(set(client._models()))


class TestTransports:
    def test_auto_tries_interactions_first(self):
        assert GeminiClient("k")._transports()[0] == "interactions"

    def test_pinned_transport(self):
        assert GeminiClient("k", transport="generatecontent")._transports() == ["generatecontent"]


class TestMissingKey:
    def test_raises_without_key(self):
        with pytest.raises(MissingApiKeyError):
            GeminiClient("").generate("hi")


class TestRealHttp:
    """Exercises the real urllib transport against the mock server."""

    def test_scan_call_uses_interactions_endpoint(self, mock_gemini):
        server = mock_gemini({"facts": {"level": 40}, "pokemon": []})
        client = GeminiClient("test-key", base_url=server.base_url)
        response = client.generate("prompt", images=[ImagePart.from_bytes(b"img")])
        assert response.transport == "interactions"
        assert response.model == "gemini-3.8-flash"
        assert server.requests[0]["path"].endswith("/interactions")

    def test_api_revision_header_is_sent(self, mock_gemini):
        server = mock_gemini({"facts": {}, "pokemon": []})
        client = GeminiClient("test-key", base_url=server.base_url)
        client.generate("prompt", images=[ImagePart.from_bytes(b"img")])
        # The revision header is what pins the interactions API shape.
        assert API_REVISION

    def test_scan_json_is_parsed(self, mock_gemini):
        server = mock_gemini({"facts": {"level": 42}, "pokemon": [{"species": "Mew"}]})
        client = GeminiClient("test-key", base_url=server.base_url)
        response = client.generate("prompt", images=[ImagePart.from_bytes(b"img")])
        assert response.json()["facts"]["level"] == 42

    def test_images_are_sent_as_base64_parts(self, mock_gemini):
        server = mock_gemini({"facts": {}, "pokemon": []})
        client = GeminiClient("test-key", base_url=server.base_url)
        client.generate("prompt", images=[ImagePart.from_bytes(b"hello")])
        parts = server.requests[0]["body"]["input"]
        image_parts = [p for p in parts if p.get("type") == "image"]
        assert image_parts and image_parts[0]["data"] == "aGVsbG8="

    def test_system_instruction_is_passed(self, mock_gemini):
        server = mock_gemini({"facts": {}, "pokemon": []})
        client = GeminiClient("test-key", base_url=server.base_url)
        client.generate("prompt", system_instruction="be strict")
        assert server.requests[0]["body"]["system_instruction"]["parts"][0]["text"] == "be strict"

    def test_response_schema_is_sent(self, mock_gemini):
        server = mock_gemini({"facts": {}, "pokemon": []})
        client = GeminiClient("test-key", base_url=server.base_url)
        client.generate("prompt", json_schema={"type": "object"})
        assert server.requests[0]["body"]["response_format"]["schema"] == {"type": "object"}


class TestErrorHandling:
    def test_http_error_becomes_gemini_error(self):
        client = GeminiClient("test-key", base_url="http://127.0.0.1:9",
                              transport="interactions")
        with pytest.raises(GeminiError):
            client.generate("prompt")

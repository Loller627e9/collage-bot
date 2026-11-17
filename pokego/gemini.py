"""Gemini client for the account scanner.

Standard library only (``urllib``), matching the bot's dependency style. Two
transports are supported because Google is mid-migration:

* ``interactions`` - ``POST {base}/v1beta/interactions`` with an ``input`` array
  of text/image parts and ``response_format`` for structured JSON.
* ``generateContent`` - ``POST {base}/v1beta/models/{model}:generateContent``
  with ``inline_data`` parts and ``generationConfig.responseSchema``.

The client prefers ``interactions`` and falls back automatically, and walks a
model list so a retired model name does not break the bot.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import random
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"
API_REVISION = "2026-05-20"

# Current first; older names kept as fallbacks. gemini-2.5-flash is deprecated
# for new API users, so it sits at the back.
DEFAULT_MODEL_FALLBACKS = (
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
)


class GeminiError(RuntimeError):
    pass


class MissingApiKeyError(GeminiError):
    pass


@dataclass
class ImagePart:
    data: bytes
    mime_type: str = "image/png"

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str = "image/png") -> "ImagePart":
        return cls(bytes(data), mime_type)

    @classmethod
    def from_path(cls, path: str | Path) -> "ImagePart":
        path = Path(path)
        mime, _ = mimetypes.guess_type(path.name)
        return cls(path.read_bytes(), mime or "image/png")

    def to_base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")


@dataclass
class GeminiResponse:
    text: str
    model: str
    transport: str
    raw: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return extract_json(self.text)


def extract_json(text: str) -> dict[str, Any]:
    """Pull a JSON object from a reply, tolerating fences and prose."""
    if not text:
        raise GeminiError("Empty model response")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].lstrip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Could not parse JSON from model response: {exc}") from exc
    raise GeminiError("Could not find a JSON object in the model response")


def _retry(fn: Callable[[], Any], *, attempts: int = 3, base_delay: float = 1.5) -> Any:
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except GeminiError as exc:
            last = exc
            if attempt == attempts - 1:
                break
            time.sleep(base_delay * (2**attempt) + random.uniform(0, 0.4))
    assert last is not None
    raise last


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        base_url: str | None = None,
        transport: str = "auto",
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.transport = (transport or "auto").lower()
        self.timeout = timeout

    def _models(self) -> list[str]:
        models = [self.model] if self.model else []
        models.extend(m for m in DEFAULT_MODEL_FALLBACKS if m not in models)
        return models

    def _transports(self) -> list[str]:
        if self.transport in {"interactions", "generatecontent"}:
            return [self.transport]
        return ["interactions", "generatecontent"]

    def generate(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        images: Sequence[ImagePart] = (),
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> GeminiResponse:
        if not self.api_key:
            raise MissingApiKeyError("GEMINI_API_KEY is not set")
        errors: list[str] = []
        for model in self._models():
            for transport in self._transports():
                try:
                    return self._call(
                        transport=transport, model=model, prompt=prompt,
                        system_instruction=system_instruction, images=images,
                        json_schema=json_schema, temperature=temperature,
                    )
                except GeminiError as exc:
                    errors.append(f"{transport}/{model}: {exc}")
                    if "404" in str(exc) or "not found" in str(exc).lower():
                        break  # model is gone; try the next one
                except urllib.error.URLError as exc:
                    errors.append(f"{transport}/{model}: network error {exc}")
        raise GeminiError("All Gemini attempts failed:\n  " + "\n  ".join(errors))

    def _call(self, *, transport: str, **kwargs: Any) -> GeminiResponse:
        if transport == "interactions":
            return self._call_interactions(**kwargs)
        return self._call_generate_content(**kwargs)

    def _call_interactions(
        self, *, model: str, prompt: str, system_instruction: str | None,
        images: Sequence[ImagePart], json_schema: dict[str, Any] | None,
        temperature: float,
    ) -> GeminiResponse:
        inputs: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image in images:
            inputs.append({"type": "image", "data": image.to_base64(),
                           "mime_type": image.mime_type})
        body: dict[str, Any] = {
            "model": model, "input": inputs,
            "generation_config": {"temperature": temperature},
        }
        if system_instruction:
            body["system_instruction"] = {"parts": [{"text": system_instruction}]}
        if json_schema is not None:
            body["response_format"] = {
                "type": "text", "mime_type": "application/json", "schema": json_schema,
            }
        payload = self._post(
            f"{self.base_url}/v1beta/interactions", body,
            {"Content-Type": "application/json", "x-goog-api-key": self.api_key,
             "Api-Revision": API_REVISION},
        )
        text = _first_text(payload)
        if not text:
            raise GeminiError(f"interactions returned no text: {_short(payload)}")
        return GeminiResponse(text, model, "interactions", payload)

    def _call_generate_content(
        self, *, model: str, prompt: str, system_instruction: str | None,
        images: Sequence[ImagePart], json_schema: dict[str, Any] | None,
        temperature: float,
    ) -> GeminiResponse:
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image in images:
            parts.append({"inline_data": {"mime_type": image.mime_type,
                                          "data": image.to_base64()}})
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature},
        }
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        if json_schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = _to_gemini_schema(json_schema)
        payload = self._post(
            f"{self.base_url}/v1beta/models/{model}:generateContent", body,
            {"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        text = _first_text(payload)
        if not text:
            raise GeminiError(f"generateContent returned no text: {_short(payload)}")
        return GeminiResponse(text, model, "generatecontent", payload)

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GeminiError(f"HTTP {exc.code} from Gemini: {_short_text(detail)}") from exc
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Non-JSON response from Gemini: {exc}") from exc


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalise to Gemini's OpenAPI subset.

    Gemini's ``Schema`` accepts ``type``, ``properties``, ``items``, ``required``,
    ``enum``, ``description`` and ``nullable``, so the structure is already
    compatible. We only drop keys Gemini rejects.
    """
    if not isinstance(schema, dict):
        return schema
    unsupported = {"$schema", "additionalProperties", "definitions"}
    out: dict[str, Any] = {}
    for key, value in schema.items():
        if key in unsupported:
            continue
        if isinstance(value, dict):
            out[key] = _to_gemini_schema(value)
        elif isinstance(value, list):
            out[key] = [_to_gemini_schema(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


def _first_text(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("output_text", "outputText"):
        if isinstance(payload.get(key), str) and payload[key]:
            return payload[key]
    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        chunks: list[str] = []
        for item in outputs:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    chunks.append(item["text"])
                for part in item.get("content") or []:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
        if chunks:
            return "".join(chunks)
    for candidate in payload.get("candidates") or []:
        content = (candidate or {}).get("content") or {}
        for part in content.get("parts") or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                return part["text"]
    return ""


def _short(payload: Any, limit: int = 400) -> str:
    try:
        return _short_text(json.dumps(payload, ensure_ascii=False))
    except (TypeError, ValueError):
        return _short_text(str(payload))


def _short_text(text: str, limit: int = 400) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."

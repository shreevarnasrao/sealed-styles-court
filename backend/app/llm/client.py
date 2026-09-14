from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class LLMError(RuntimeError):
    pass


class LLMClient:
    """OpenAI-compatible client with retry + multi-provider fallback.

    Primary: GROQ_API_KEY / LLM_BASE_URL. Fallback: OPENAI_API_KEY at api.openai.com
    if the primary returns 429/5xx. Small and explicit — no SDK dependency.
    """

    def __init__(self) -> None:
        self.base_url = LLM_BASE_URL.rstrip("/")
        self.api_key = LLM_API_KEY
        self.model = LLM_MODEL
        import os as _os

        self._fallback_url = "https://api.openai.com/v1"
        self._fallback_key = _os.getenv("OPENAI_API_KEY", "")
        self._fallback_model = _os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def complete_json(self, system: str, user: str, retries: int = 1) -> dict[str, Any]:
        if not self.available:
            raise LLMError("No LLM API key configured")
        last_err = "unknown"
        for _ in range(retries + 1):
            raw = await self._chat(system, user)
            parsed = _extract_json(raw)
            if parsed is not None:
                return parsed
            last_err = raw[:300]
            user = user + "\n\nReturn ONLY valid JSON matching the schema. No markdown."
        raise LLMError(f"Could not parse JSON from model: {last_err}")

    async def complete_text(self, system: str, user: str) -> str:
        if not self.available:
            raise LLMError("No LLM API key configured")
        return await self._chat(system, user)

    async def _chat(self, system: str, user: str) -> str:
        import asyncio

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        # Retry with exponential backoff; fall back to OpenAI on 429/5xx.
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    if r.status_code == 400:
                        payload.pop("response_format", None)
                        r = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    if r.status_code in (429, 500, 502, 503) and self._fallback_key:
                        r2 = await client.post(
                            f"{self._fallback_url}/chat/completions",
                            headers={"Authorization": f"Bearer {self._fallback_key}", "Content-Type": "application/json"},
                            json={**payload, "model": self._fallback_model},
                        )
                        r2.raise_for_status()
                        return r2.json()["choices"][0]["message"]["content"]
                    r.raise_for_status()
                    data = r.json()
                return data["choices"][0]["message"]["content"]
            except (httpx.HTTPError, KeyError, ValueError) as e:
                last_err = e
                await asyncio.sleep(0.5 * (2**attempt))
        raise LLMError(f"LLM request failed after retries: {last_err}")


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        m = JSON_BLOCK.search(text)
        if not m:
            return None
        try:
            val = json.loads(m.group(0))
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            return None

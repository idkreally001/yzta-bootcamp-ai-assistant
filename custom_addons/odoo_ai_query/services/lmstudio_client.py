import json
import logging
import os
import re

import requests

from .llm_client import LLMClient

_logger = logging.getLogger(__name__)


class LMStudioClient(LLMClient):
    """LM Studio local server, OpenAI-compatible /v1/chat/completions API."""

    def __init__(self, base_url=None, model=None):
        self.base_url = base_url or os.environ.get("LMSTUDIO_URL", "http://localhost:1234/v1")
        self.model = model or os.environ.get("LMSTUDIO_MODEL", "local-model")

    def _call(self, system_prompt, user_prompt):
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            _logger.error("Unexpected LM Studio response shape: %s", data)
            raise ValueError("LM Studio returned no usable content") from exc

    def complete_json(self, system_prompt, user_prompt):
        raw = self._call(
            system_prompt + "\n\nRespond with JSON only, no prose, no markdown fences.",
            user_prompt,
        )
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            _logger.error("LM Studio returned invalid JSON: %s", raw)
            raise ValueError(f"Invalid JSON from LM Studio: {exc}") from exc

    def complete_text(self, system_prompt, user_prompt):
        return self._call(system_prompt, user_prompt)

    def stream_text(self, system_prompt, user_prompt):
        with requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "stream": True,
            },
            timeout=120,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                payload_str = raw_line[len("data:"):].strip()
                if payload_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                text = delta.get("content")
                if text:
                    yield text

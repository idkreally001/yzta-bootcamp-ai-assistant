import json
import logging
import os
import re

import requests

from .llm_client import LLMClient

_logger = logging.getLogger(__name__)

# Primary + fallback model, in order. Both are free-tier "Lite" models with
# separate rate-limit buckets (15 rpm / 500 rpd each) — falling back on 429
# roughly doubles effective throughput without any cost.
GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


class GeminiClient(LLMClient):
    def __init__(self, api_key=None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY not set")

    def _call(self, system_prompt, user_prompt, json_mode):
        combined_input = f"{system_prompt}\n\n{user_prompt}"
        last_exc = None

        for model in GEMINI_MODELS:
            payload = {
                "model": model,
                "input": combined_input,
                "store": False,
            }
            if json_mode:
                payload["response_format"] = {
                    "type": "text",
                    "mime_type": "application/json",
                }
            resp = requests.post(
                GEMINI_URL,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if resp.status_code == 429:
                _logger.warning("Gemini model %s rate-limited, trying next fallback", model)
                last_exc = requests.HTTPError(f"429 rate limited on {model}", response=resp)
                continue

            resp.raise_for_status()
            data = resp.json()

            if data.get("status") != "completed":
                _logger.error("Gemini interaction not completed: %s", data)
                raise ValueError(f"Gemini interaction status: {data.get('status')}")

            for step in reversed(data.get("steps", [])):
                if step.get("type") == "model_output":
                    parts = step.get("content", [])
                    text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
                    if text_parts:
                        return "".join(text_parts)

            _logger.error("No model_output step found in Gemini response: %s", data)
            raise ValueError("Gemini returned no usable content")

        raise last_exc or RuntimeError("All Gemini fallback models exhausted")

    def complete_json(self, system_prompt, user_prompt):
        raw = self._call(system_prompt, user_prompt, json_mode=True)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            _logger.error("Gemini returned invalid JSON: %s", raw)
            raise ValueError(f"Invalid JSON from Gemini: {exc}") from exc

    def complete_text(self, system_prompt, user_prompt):
        return self._call(system_prompt, user_prompt, json_mode=False)

    def stream_text(self, system_prompt, user_prompt):
        """Yield text chunks from the summarize step as they stream in.

        Only the primary model is used here (no 429 fallback mid-stream —
        falling back after tokens have already started rendering would be
        confusing to watch), which is acceptable since streaming is only
        used for the final, already-non-critical summary step.
        """
        combined_input = f"{system_prompt}\n\n{user_prompt}"
        payload = {
            "model": GEMINI_MODELS[0],
            "input": combined_input,
            "store": False,
            "stream": True,
        }
        with requests.post(
            GEMINI_URL,
            headers={
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            event_type = None
            # Decode bytes as UTF-8 ourselves — requests' decode_unicode=True
            # guesses the response encoding and can get it wrong for SSE
            # streams, silently mangling non-ASCII (Turkish) characters.
            for raw_bytes in resp.iter_lines(decode_unicode=False):
                raw_line = raw_bytes.decode("utf-8") if raw_bytes else ""
                if not raw_line:
                    continue
                if raw_line.startswith("event:"):
                    event_type = raw_line[len("event:"):].strip()
                    continue
                if raw_line.startswith("data:"):
                    payload_str = raw_line[len("data:"):].strip()
                    if payload_str == "[DONE]":
                        break
                    try:
                        event_data = json.loads(payload_str)
                    except json.JSONDecodeError:
                        continue
                    if event_type == "step.delta":
                        delta = event_data.get("delta", {})
                        if delta.get("type") == "text":
                            text = delta.get("text", "")
                            if text:
                                yield text

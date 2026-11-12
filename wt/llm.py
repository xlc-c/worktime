"""Minimal client for a local OpenAI-compatible LLM server (llama.cpp / Ollama).

Only 127.0.0.1 is used; no API keys, no cloud endpoints. If the server is not
running the pipeline falls back to deterministic naming.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request

log = logging.getLogger("worktime.llm")


class LlmClient:
    def __init__(self, cfg: dict):
        section = cfg.get("llm", {})
        self.base_url = str(section.get("base_url") or "http://127.0.0.1:8080").rstrip("/")
        self.model = str(section.get("model") or "qwen3-4b")
        self.timeout = float(section.get("timeout_s") or 240)
        self.max_tokens = int(section.get("max_tokens") or 900)

    # ------------------------------------------------------------------
    def health(self) -> bool:
        for path in ("/health", "/v1/models"):
            try:
                req = urllib.request.Request(self.base_url + path, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status < 500:
                        return True
            except Exception:
                continue
        return False

    def chat(self, system: str, user: str, temperature: float = 0.1) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        req = urllib.request.Request(
            self.base_url + "/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        return body["choices"][0]["message"]["content"]


def extract_json(text: str):
    """Pull the first JSON object/array out of a model response."""
    if not text:
        return None
    # strip ```json fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return None

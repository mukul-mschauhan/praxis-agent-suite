"""
core/claude_client.py
Thin wrapper around the Anthropic Claude API. Centralizes model choice,
JSON-extraction, retries, and token/latency tracking so every agent call
is measured consistently for the trace viewer.
"""
import json
import re
import time
import anthropic

MODEL = "claude-sonnet-4-6"


class ClaudeClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Anthropic API key is required.")
        self.client = anthropic.Anthropic(api_key=api_key)

    def call(self, system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> dict:
        """
        Calls Claude with a given skill's system prompt + a user prompt.
        Returns a dict with the raw text, parsed JSON (if possible), latency, and token usage.
        """
        start = time.time()
        response = self.client.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        latency = round(time.time() - start, 2)

        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

        parsed = self._extract_json(raw_text)

        return {
            "raw_text": raw_text,
            "parsed": parsed,
            "latency_seconds": latency,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

    @staticmethod
    def _extract_json(text: str):
        """Strips markdown fences and pulls the first valid JSON object out of a response."""
        cleaned = re.sub(r"```json|```", "", text).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return None
            return None

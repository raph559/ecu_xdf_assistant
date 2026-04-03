from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List


class LMStudioClient:
    def __init__(self, host: str, timeout_seconds: int = 180) -> None:
        base = host.rstrip("/")
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        self.host = base
        self.timeout_seconds = timeout_seconds

    def chat_structured(
        self,
        model: str,
        messages: List[Dict[str, str]],
        schema: Dict[str, Any],
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "candidate_judgement",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        raw = self._post_json("/chat/completions", payload)
        response = json.loads(raw)
        choices = response.get("choices", [])
        if not choices:
            raise RuntimeError("LM Studio returned no choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if not content:
            raise RuntimeError("LM Studio returned an empty structured response.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"LM Studio returned invalid JSON: {content}") from exc

    def list_loaded_models(self) -> List[str]:
        raw = self._get("/models")
        payload = json.loads(raw)
        return [str(item.get("id", "")).strip() for item in payload.get("data", []) if str(item.get("id", "")).strip()]

    def _get(self, path: str) -> str:
        request = urllib.request.Request(
            url=f"{self.host}{path}",
            headers={"Content-Type": "application/json"},
            method="GET",
        )
        return self._request(request)

    def _post_json(self, path: str, payload: Dict[str, Any]) -> str:
        request = urllib.request.Request(
            url=f"{self.host}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return self._request(request)

    def _request(self, request: urllib.request.Request) -> str:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LM Studio HTTP error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to contact LM Studio at {self.host}: {exc}") from exc

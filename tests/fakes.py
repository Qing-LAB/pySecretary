from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import requests


class NoJson:
    pass


NO_JSON = NoJson()


class FakeResponse:
    def __init__(
        self,
        payload: Any = None,
        *,
        text: str = "",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
    ) -> None:
        self._payload = payload if payload is not None else {}
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content

    def json(self) -> Any:
        if self._payload is NO_JSON:
            raise ValueError("response is not JSON")
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


@dataclass
class FakeSession:
    get_map: dict[str, FakeResponse] = field(default_factory=dict)
    post_map: dict[str, FakeResponse] = field(default_factory=dict)
    get_calls: list[dict[str, Any]] = field(default_factory=list)
    post_calls: list[dict[str, Any]] = field(default_factory=list)

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        path = urlparse(url).path
        self.get_calls.append({"url": url, "path": path, **kwargs})
        return self.get_map.get(path, FakeResponse(status_code=404))

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        path = urlparse(url).path
        self.post_calls.append({"url": url, "path": path, **kwargs})
        return self.post_map.get(path, FakeResponse(status_code=404))


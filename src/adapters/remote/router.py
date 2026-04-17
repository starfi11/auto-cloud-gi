from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

Handler = Callable[["Request"], "Response"]


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    params: dict[str, str] = field(default_factory=dict)
    query: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def header(self, name: str, default: str = "") -> str:
        key = name.lower()
        for k, v in self.headers.items():
            if k.lower() == key:
                return v
        return default


@dataclass(frozen=True)
class Response:
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)

    def render(self) -> tuple[int, dict[str, str], bytes | None, str | None]:
        """Return (status, headers, body_bytes, file_path).

        Subclasses override. Base Response returns an empty body so it can be
        used for 204-style empties when needed.
        """
        return self.status, dict(self.headers), b"", None


@dataclass(frozen=True)
class JsonResponse(Response):
    payload: Any = None

    def render(self) -> tuple[int, dict[str, str], bytes | None, str | None]:
        import json

        body = json.dumps(self.payload, ensure_ascii=False).encode("utf-8")
        hdrs = dict(self.headers)
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
        return self.status, hdrs, body, None


@dataclass(frozen=True)
class TextResponse(Response):
    text: str = ""
    content_type: str = "text/plain; charset=utf-8"

    def render(self) -> tuple[int, dict[str, str], bytes | None, str | None]:
        body = self.text.encode("utf-8")
        hdrs = dict(self.headers)
        hdrs.setdefault("Content-Type", self.content_type)
        return self.status, hdrs, body, None


@dataclass(frozen=True)
class BytesResponse(Response):
    body: bytes = b""
    content_type: str = "application/octet-stream"

    def render(self) -> tuple[int, dict[str, str], bytes | None, str | None]:
        hdrs = dict(self.headers)
        hdrs.setdefault("Content-Type", self.content_type)
        return self.status, hdrs, self.body, None


@dataclass(frozen=True)
class FileResponse(Response):
    path: str = ""
    content_type: str = "application/octet-stream"

    def render(self) -> tuple[int, dict[str, str], bytes | None, str | None]:
        hdrs = dict(self.headers)
        hdrs.setdefault("Content-Type", self.content_type)
        return self.status, hdrs, None, self.path


@dataclass(frozen=True)
class RouteMatch:
    handler: Handler
    params: dict[str, str]


def _compile_template(template: str) -> re.Pattern[str]:
    # Escape the template then swap escaped placeholders back to named groups.
    # Supports:
    #   {name}   — single path segment (no slash)
    #   {*name}  — greedy tail spanning multiple segments
    escaped = re.escape(template)

    def _single(match: re.Match[str]) -> str:
        return f"(?P<{match.group(1)}>[^/]+)"

    def _greedy(match: re.Match[str]) -> str:
        return f"(?P<{match.group(1)}>.+)"

    pattern = re.sub(r"\\\{\\\*([A-Za-z_][A-Za-z0-9_]*)\\\}", _greedy, escaped)
    pattern = re.sub(r"\\\{([A-Za-z_][A-Za-z0-9_]*)\\\}", _single, pattern)
    return re.compile(f"^{pattern}$")


class Router:
    def __init__(self) -> None:
        self._routes: list[tuple[str, re.Pattern[str], Handler, str]] = []

    def register(self, method: str, path_template: str, handler: Handler) -> None:
        self._routes.append((method.upper(), _compile_template(path_template), handler, path_template))

    def route(self, method: str, path_template: str) -> Callable[[Handler], Handler]:
        def _wrap(fn: Handler) -> Handler:
            self.register(method, path_template, fn)
            return fn

        return _wrap

    def get(self, path_template: str) -> Callable[[Handler], Handler]:
        return self.route("GET", path_template)

    def post(self, path_template: str) -> Callable[[Handler], Handler]:
        return self.route("POST", path_template)

    def match(self, method: str, path: str) -> RouteMatch | None:
        m = method.upper()
        for route_method, pattern, handler, _tpl in self._routes:
            if route_method != m:
                continue
            matched = pattern.match(path)
            if matched is None:
                continue
            return RouteMatch(handler=handler, params=dict(matched.groupdict()))
        return None

    def method_allowed(self, path: str) -> list[str]:
        """Return list of methods registered for a path. Helps emit 405."""
        allowed: list[str] = []
        for route_method, pattern, _handler, _tpl in self._routes:
            if pattern.match(path) is not None:
                allowed.append(route_method)
        return allowed

    def templates(self) -> Iterable[tuple[str, str]]:
        return [(m, tpl) for m, _p, _h, tpl in self._routes]

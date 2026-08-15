"""Cross-repo federation — query a remote ArchLens HTTP/SSE endpoint or export URL."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def fetch_remote_architecture(url: str, timeout: float = 30.0) -> dict[str, Any]:
    """
    Fetch architecture JSON from a remote URL.

    Supports:
      - Direct architecture.json export URLs
      - ArchLens HTTP endpoints that return snapshot JSON
    """
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "archlens-federation/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Remote fetch failed ({e.code}): {url}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Remote unreachable: {url} ({e.reason})") from e


def query_remote_tool(base_url: str, tool: str, arguments: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    """
    Best-effort HTTP bridge for remote ArchLens tool invocation.

    Expected optional endpoint shapes:
      POST {base_url}/tools/{tool}  JSON body = arguments
      GET  {base_url}/export
    """
    if tool == "export":
        return fetch_remote_architecture(base_url.rstrip("/") + "/export", timeout=timeout)

    url = f"{base_url.rstrip('/')}/tools/{tool}"
    data = json.dumps(arguments).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "archlens-federation/0.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # Fallback: if remote only exposes export JSON
        if e.code == 404:
            return fetch_remote_architecture(base_url)
        raise RuntimeError(f"Remote tool call failed ({e.code}): {tool}") from e

"""Minimal GraphQL client for OTP's `/otp/gtfs/v1` endpoint.

Stdlib-only on purpose: this spike does not need a generic GraphQL client
library for two saved queries. No public proxy is exposed; every call goes
to a loopback URL the spike itself started.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

INTROSPECTION_QUERY = """
query IntrospectSchema {
  __schema {
    queryType { name }
    types { name kind }
  }
}
"""


@dataclass(frozen=True)
class GraphQLResult:
    status: str  # "ok" | "otp_unavailable" | "graphql_error"
    data: dict[str, Any] | None = None
    errors: list[dict[str, Any]] | None = None


def post_query(
    url: str,
    query: str,
    variables: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
) -> GraphQLResult:
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
        return GraphQLResult("otp_unavailable", errors=[{"message": str(exc)}])
    except ValueError as exc:  # body was not valid UTF-8 JSON
        return GraphQLResult("graphql_error", errors=[{"message": f"invalid response body: {exc}"}])

    if not isinstance(body, dict):
        return GraphQLResult("graphql_error", errors=[{"message": "response body is not a JSON object"}])
    if body.get("errors"):
        return GraphQLResult("graphql_error", data=body.get("data"), errors=body["errors"])
    return GraphQLResult("ok", data=body.get("data"))


def save_introspection(url: str, out_path: Path) -> GraphQLResult:
    result = post_query(url, INTROSPECTION_QUERY)
    if result.status == "ok" and result.data is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as handle:
            json.dump(result.data, handle, indent=2, sort_keys=True)
    return result

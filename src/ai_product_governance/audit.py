"""Audit trail for the MCP server: one JSON line per tool call.

Each line records when the call happened (UTC), which tool was called, the policy in force, a SHA-256 hash of
the arguments, whether the call succeeded, the tier `classify_risk_tier` returned, and who called, as far as the
transport can tell. Arguments are hashed rather than stored, and bearer tokens never reach the log: the record
holds only the principal name the token verifier assigns.

The log fails closed. If a line cannot be written, the client gets an error instead of the result, so no
result leaves the server unrecorded.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp_types import INTERNAL_ERROR
from pydantic import BaseModel

from ai_product_governance import __version__
from ai_product_governance.policy import EffectivePolicy

logger = logging.getLogger(__name__)


def arguments_sha256(arguments: Any) -> str:
    """Hash tool arguments as canonical JSON: `json.dumps(arguments, sort_keys=True, separators=(",", ":"))`."""
    canonical = json.dumps({} if arguments is None else arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class AuditLog:
    """An append-only JSON Lines file. One instance can be shared by concurrent calls."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        # Open it now so a bad path stops the server at start-up rather than failing the first call.
        with self.path.open("ab"):
            pass

    def append(self, record: dict[str, Any]) -> None:
        line = (json.dumps(record, separators=(",", ":"), default=str) + "\n").encode("utf-8")
        # Reopening per line keeps the log compatible with external rotation; the lock and a single write per
        # line keep lines whole when calls finish at the same time.
        with self._lock, self.path.open("ab") as handle:
            handle.write(line)


class AuditMiddleware:
    """MCP server middleware that writes an audit line for every `tools/call` request."""

    def __init__(self, log: AuditLog, policy: EffectivePolicy) -> None:
        self.log = log
        self.policy = policy

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)
        try:
            result = await call_next(ctx)
        except Exception:
            self._write(ctx, None, failed=True)
            raise
        self._write(ctx, result, failed=False)
        return result

    def _write(self, ctx: ServerRequestContext[Any, Any], result: HandlerResult, *, failed: bool) -> None:
        record = self._record(ctx, result, failed=failed)
        try:
            self.log.append(record)
        except OSError as exc:
            logger.exception("Could not write to the audit log %s", self.log.path)
            raise MCPError(INTERNAL_ERROR, "The audit log could not be written, so the result was withheld.") from exc

    def _record(self, ctx: ServerRequestContext[Any, Any], result: HandlerResult, *, failed: bool) -> dict[str, Any]:
        params = ctx.params or {}
        tool = params.get("name")
        is_error, structured = _result_fields(result)
        ok = not failed and not is_error
        tier = None
        if ok and tool == "classify_risk_tier" and isinstance(structured, dict):
            tier = (structured.get("tier") or {}).get("id")
        return {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "event": "tools/call",
            "tool": tool if isinstance(tool, str) else None,
            "outcome": "ok" if ok else "error",
            "tier": tier,
            "policy_id": self.policy.id,
            "policy_version": self.policy.version,
            "arguments_sha256": arguments_sha256(params.get("arguments")),
            "client": client_identity(ctx),
            "server_version": __version__,
        }


def client_identity(ctx: ServerRequestContext[Any, Any]) -> dict[str, str | None]:
    """Who made the request, from what the transport provides.

    `principal` is authenticated (it comes from the bearer-token verifier); `name` and `version` are what the
    client reports about itself; `address` is the HTTP peer. Fields the transport cannot supply are null, so
    a stdio call records only the client's self-reported name and version.
    """
    token = get_access_token()
    client_params = getattr(ctx.session, "client_params", None)
    info = getattr(client_params, "client_info", None)
    peer = getattr(ctx.request, "client", None)
    return {
        "principal": token.client_id if token is not None else None,
        "name": getattr(info, "name", None),
        "version": getattr(info, "version", None),
        "address": getattr(peer, "host", None),
    }


def _result_fields(result: HandlerResult) -> tuple[bool, Any]:
    """(is_error, structured content) from a tool result, whether the SDK passes a model or a dict."""
    if isinstance(result, BaseModel):
        return bool(getattr(result, "is_error", False)), getattr(result, "structured_content", None)
    if isinstance(result, dict):
        return bool(result.get("isError", False)), result.get("structuredContent")
    return False, None

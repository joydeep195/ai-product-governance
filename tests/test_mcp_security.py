"""Running the MCP server as a shared service: bearer-token auth, the loopback rule and the audit log."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError

from ai_product_governance import __version__
from ai_product_governance import mcp_server as mcp_server_module
from ai_product_governance.audit import AuditLog
from ai_product_governance.cli import main
from ai_product_governance.mcp_server import (
    TOKEN_ENV,
    TOKEN_PRINCIPAL,
    ServerConfigError,
    StaticTokenVerifier,
    build_server,
    read_token,
)

AUDIT_FIELDS = {
    "timestamp",
    "event",
    "tool",
    "outcome",
    "tier",
    "policy_id",
    "policy_version",
    "arguments_sha256",
    "client",
    "server_version",
}
HIGH_RISK_ANSWERS = {"answers": {"consequential_decisions": True}}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def audit_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(autouse=True)
def _no_ambient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_ENV, raising=False)


@pytest.fixture
def token() -> str:
    return secrets.token_urlsafe(32)


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[tuple[MCPServer[Any], str, dict[str, Any]]]:
    """Replace MCPServer.run so `aipg serve` returns instead of listening, and record what it would have run."""
    calls: list[tuple[MCPServer[Any], str, dict[str, Any]]] = []

    def fake_run(self: MCPServer[Any], transport: str = "stdio", **kwargs: Any) -> None:
        calls.append((self, transport, kwargs))

    monkeypatch.setattr(MCPServer, "run", fake_run)
    return calls


async def post_without_lifespan(server: MCPServer[Any], headers: dict[str, str]) -> httpx2.Response:
    """POST to the HTTP app in-process. Enough to see the auth layer's answer, which comes before any session."""
    app = server.streamable_http_app(host="127.0.0.1")
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        return await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers)


# --------------------------------------------------------------------------- tokens


def test_token_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    assert read_token() is None
    monkeypatch.setenv(TOKEN_ENV, f"  {token}\n")
    assert read_token() == token


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16"])
def test_token_file_wins_over_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str, encoding: str
) -> None:
    # utf-8-sig is what Notepad may write; utf-16 is Windows PowerShell's default for `Out-File`.
    path = tmp_path / "token"
    path.write_text(token + "\r\n", encoding=encoding)
    monkeypatch.setenv(TOKEN_ENV, secrets.token_urlsafe(32))
    assert read_token(str(path)) == token


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read"),
        ("", "is empty"),
        ("short-token", "at least 32"),
        ("a" * 40 + "\n" + "b" * 40, "single line"),
    ],
)
def test_unusable_token_files_are_refused(tmp_path: Path, content: str | None, message: str) -> None:
    path = tmp_path / "token"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ServerConfigError, match=message) as caught:
        read_token(str(path))
    if content:
        assert content not in str(caught.value), "error messages must not echo the token"


def test_verifier_accepts_only_the_exact_token(token: str) -> None:
    verifier = StaticTokenVerifier(token)
    accepted = run(verifier.verify_token(token))
    assert accepted is not None
    assert accepted.client_id == TOKEN_PRINCIPAL
    assert token not in repr(accepted), "the verified token must not be kept where the SDK might log it"
    for wrong in ("", token[:-1], token + "x", token.upper(), secrets.token_urlsafe(32)):
        assert run(verifier.verify_token(wrong)) is None


def test_verifier_compares_in_constant_time(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    compared: list[tuple[bytes, bytes]] = []
    real = mcp_server_module.hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        compared.append((a, b))
        return real(a, b)

    monkeypatch.setattr(mcp_server_module.hmac, "compare_digest", spy)
    run(StaticTokenVerifier(token).verify_token("x"))
    run(StaticTokenVerifier(token).verify_token(token))
    assert len(compared) == 2
    # Fixed-length digests, so the comparison time does not depend on the length of the guess either.
    assert all(len(a) == len(b) == 32 for a, b in compared)


# --------------------------------------------------------------------------- HTTP auth, in-process


def test_http_requires_a_token(token: str) -> None:
    response = run(post_without_lifespan(build_server(token=token), {}))
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Bearer ")


@pytest.mark.parametrize("scheme", ["Bearer {wrong}", "Bearer {prefix}", "Basic {token}", "{token}"])
def test_http_rejects_a_wrong_token(token: str, scheme: str) -> None:
    header = scheme.format(wrong=secrets.token_urlsafe(32), prefix=token[:-1], token=token)
    response = run(post_without_lifespan(build_server(token=token), {"Authorization": header}))
    assert response.status_code == 401


# --------------------------------------------------------------------------- start-up rules


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "127.0.0.2", "governance.internal"])  # noqa: S104
def test_non_loopback_host_is_refused_without_a_token(
    host: str, started: list[Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["serve", "--transport", "streamable-http", "--host", host]) == 2
    assert not started, "the server must not start"
    error = capsys.readouterr().err
    assert f"refusing to listen on {host} without authentication" in error
    assert TOKEN_ENV in error and "--token-file" in error


def test_non_loopback_host_starts_with_a_token_file(tmp_path: Path, token: str, started: list[Any]) -> None:
    path = tmp_path / "token"
    path.write_text(token, encoding="utf-8")
    argv = ["serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9123", "--token-file", str(path)]  # noqa: S104
    assert main(argv) == 0
    [(server, transport, kwargs)] = started
    assert (transport, kwargs) == ("streamable-http", {"host": "0.0.0.0", "port": 9123})  # noqa: S104
    assert run(post_without_lifespan(server, {})).status_code == 401


def test_loopback_host_starts_without_a_token(started: list[Any]) -> None:
    assert main(["serve", "--transport", "streamable-http"]) == 0
    [(_server, transport, kwargs)] = started
    assert (transport, kwargs) == ("streamable-http", {"host": "127.0.0.1", "port": 8000})


def test_token_file_is_refused_for_stdio(tmp_path: Path, token: str, started: list[Any]) -> None:
    path = tmp_path / "token"
    path.write_text(token, encoding="utf-8")
    assert main(["serve", "--token-file", str(path)]) == 2
    assert not started


def test_unwritable_audit_log_stops_start_up(tmp_path: Path, started: list[Any]) -> None:
    assert main(["serve", "--audit-log", str(tmp_path / "missing" / "audit.jsonl")]) == 2
    assert not started


# --------------------------------------------------------------------------- audit log


def test_audit_lines_have_the_documented_shape(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"

    async def scenario() -> None:
        async with Client(build_server(audit_log=path)) as client:
            await client.call_tool("classify_risk_tier", HIGH_RISK_ANSWERS)
            await client.call_tool("get_policy", {})
            await client.call_tool("classify_risk_tier", {"answers": {"bogus": True}})

    run(scenario())
    lines = audit_lines(path)
    assert [set(line) for line in lines] == [AUDIT_FIELDS] * 3
    assert [(line["tool"], line["outcome"], line["tier"]) for line in lines] == [
        ("classify_risk_tier", "ok", "high"),
        ("get_policy", "ok", None),
        ("classify_risk_tier", "error", None),
    ]
    first = lines[0]
    assert first["timestamp"].endswith("Z")
    assert datetime.fromisoformat(first["timestamp"]).tzinfo == UTC
    assert first["event"] == "tools/call"
    assert (first["policy_id"], first["policy_version"]) == ("aipg-default", "1.1.0")
    assert first["server_version"] == __version__
    canonical = json.dumps(HIGH_RISK_ANSWERS, sort_keys=True, separators=(",", ":"))
    assert first["arguments_sha256"] == hashlib.sha256(canonical.encode()).hexdigest()
    assert lines[1]["arguments_sha256"] == hashlib.sha256(b"{}").hexdigest()
    # In-process there is no authenticated principal or network peer; the client still names itself.
    assert first["client"]["principal"] is None and first["client"]["address"] is None
    assert isinstance(first["client"]["name"], str)
    assert "consequential_decisions" not in path.read_text(encoding="utf-8"), "arguments are hashed, not stored"


def test_audit_log_appends_whole_lines_under_concurrency(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text('{"earlier": "line"}\n', encoding="utf-8")

    async def scenario() -> None:
        async with Client(build_server(audit_log=path)) as client:
            await asyncio.gather(*(client.call_tool("classify_risk_tier", HIGH_RISK_ANSWERS) for _ in range(20)))

    run(scenario())
    log = AuditLog(path)

    def write(worker: int) -> None:
        for i in range(100):
            log.append({"worker": worker, "i": i, "pad": "x" * 500})

    workers = [threading.Thread(target=write, args=(n,)) for n in range(8)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    lines = audit_lines(path)  # every line parses, so none was interleaved
    assert lines[0] == {"earlier": "line"}, "the log is appended to, never truncated"
    assert sum(1 for line in lines if line.get("tool") == "classify_risk_tier") == 20
    assert sorted((line["worker"], line["i"]) for line in lines if "worker" in line) == [
        (n, i) for n in range(8) for i in range(100)
    ]


def test_audit_log_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    server = build_server(audit_log=path)
    path.unlink()
    path.mkdir()  # the log can no longer be written

    async def scenario() -> None:
        async with Client(server) as client:
            with pytest.raises(MCPError, match="audit log could not be written"):
                await client.call_tool("classify_risk_tier", HIGH_RISK_ANSWERS)

    run(scenario())


# --------------------------------------------------------------------------- end to end over HTTP


@dataclass
class HttpServer:
    url: str
    token: str
    audit_log: Path
    output: Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@pytest.fixture(scope="module")
def http_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[HttpServer]:
    """`aipg serve --transport streamable-http` in a subprocess, with the token in the environment."""
    root = tmp_path_factory.mktemp("http")
    token = secrets.token_urlsafe(32)
    port = _free_port()
    audit_log, output = root / "audit.jsonl", root / "server.log"
    env = {**os.environ, TOKEN_ENV: token}
    env.pop("AIPG_POLICY", None)
    command = [sys.executable, "-m", "ai_product_governance", "serve", "--transport", "streamable-http"]
    command += ["--port", str(port), "--audit-log", str(audit_log)]
    with output.open("wb") as sink:
        process = subprocess.Popen(command, env=env, stdout=sink, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 60
        while True:
            if process.poll() is not None:
                pytest.fail(f"server exited early:\n{output.read_text(encoding='utf-8', errors='replace')}")
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    pytest.fail("server did not start listening within 60 seconds")
                time.sleep(0.2)
        yield HttpServer(f"http://127.0.0.1:{port}/mcp", token, audit_log, output)
    finally:
        process.terminate()
        process.wait(timeout=30)


def test_http_end_to_end_rejects_missing_and_wrong_tokens(http_server: HttpServer) -> None:
    async def scenario() -> None:
        async with httpx2.AsyncClient() as client:
            for headers in ({}, {"Authorization": f"Bearer {secrets.token_urlsafe(32)}"}):
                response = await client.post(
                    http_server.url, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers=headers
                )
                assert response.status_code == 401

    run(scenario())


def test_http_end_to_end_serves_the_token_holder_and_audits_the_call(http_server: HttpServer) -> None:
    async def scenario() -> None:
        headers = {"Authorization": f"Bearer {http_server.token}"}
        async with (
            httpx2.AsyncClient(headers=headers) as http,
            Client(streamable_http_client(http_server.url, http_client=http)) as client,
        ):
            result = await client.call_tool("classify_risk_tier", HIGH_RISK_ANSWERS)
            assert result.structured_content is not None
            assert result.structured_content["tier"]["id"] == "high"

    run(scenario())
    [line] = [line for line in audit_lines(http_server.audit_log) if line["tool"] == "classify_risk_tier"]
    assert line["tier"] == "high" and line["outcome"] == "ok"
    assert line["client"]["principal"] == TOKEN_PRINCIPAL
    assert line["client"]["address"] == "127.0.0.1"
    assert http_server.token not in http_server.audit_log.read_text(encoding="utf-8")
    assert http_server.token not in http_server.output.read_text(encoding="utf-8", errors="replace")

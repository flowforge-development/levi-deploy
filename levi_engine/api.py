#!/usr/bin/env python3
"""Levi — the Scripture beating heart. One HTTP door, scripture only.

Per-account data (notebooks, memory, study graphs) lives on the user's side:
Ritual owns that brain and exposes it to Levi through its own API.

Run: LEVI_DB_PATH=/data/levi.db python3 -m levi_engine.api --host 0.0.0.0 --port 8777
Gate: set LEVI_API_KEY to require `Authorization: Bearer <key>` on every request.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import query

API_KEY = os.environ.get("LEVI_API_KEY", "")

# Tools that write to the host (backups) are not offered on the public door.
MCP_BLOCKED = {"levi_backup"}


class Handler(BaseHTTPRequestHandler):
    def _authed(self) -> bool:
        if not API_KEY:
            return True
        header = self.headers.get("Authorization", "")
        return (hmac.compare_digest(header, f"Bearer {API_KEY}")
                or hmac.compare_digest(header, API_KEY))

    def _send(self, obj, code=200, cache=True):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
        if API_KEY:
            self.send_header("Vary", "Authorization")
        if code == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="levi"')
        if cache and code < 400:
            if API_KEY:
                # Auth-gated data must never land in a shared edge cache.
                self.send_header("Cache-Control", "private, max-age=300, stale-while-revalidate=600")
            else:
                self.send_header("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800")
        else:
            self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD" and (not isinstance(obj, (dict, list)) or body != b"{}" or code < 400):
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        # /health stays public so the container healthcheck and uptime probes work.
        if u.path != "/health" and not self._authed():
            return self._send({"error": "unauthorized"}, 401)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        if u.path == "/mcp":
            return self._send({"error": "method not allowed"}, 405, cache=False)
        try:
            if u.path in ("/", "/help"):
                return self._send({"name": "levi", "one_api": "GET /query?ref=<ref>&caps=text,interlinear,context,language,purpose,chunks,crossref,ancient,topics,semantic,graph", "endpoints": [
                    "/verse?ref=John 3:16", "/interlinear?ref=John 3:16",
                    "/context?ref=John 3:16", "/language?ref=Daniel 2:4",
                    "/purpose?ref=Ezekiel 27", "/chunks?ref=Genesis 1:1",
                    "/crossref?ref=Rom 8:28", "/search?q=living water&limit=20",
                    "/word?q=H7307", "/topic?q=grace", "/commentary?ref=John 3:16",
                    "/overlap?book=Romans", "/character?q=Moses", "/ancient?ref=Genesis 1:1",
                    "/sefaria?ref=Genesis 1:1", "/semantic?q=grace&limit=6", "/graph_neighbors?ref=Romans 5", "/books", "/random", "/stats", "/doctor",
                    "/study?q=living water&limit=6"],
                    "mcp": "POST /mcp (MCP over HTTP, JSON-RPC)",
                    "auth": "Authorization: Bearer <key>"})
            if u.path == "/query":
                return self._send(query.multi(q.get("ref", ""), caps=q.get("caps", ""),
                                              q=q.get("q", ""), limit=int(q.get("limit", 20))))
            if u.path == "/study":
                data = query.study_bundle(q=q.get("q", ""), ref=q.get("ref", ""),
                                          limit=q.get("limit", 6))
                return self._send(data, 200 if data["count"] else 404, cache=False)
            if u.path == "/verse":
                data = query.get_verse(q.get("ref", ""))
                return self._send(data, 200 if data else 404)
            if u.path == "/interlinear":
                data = query.interlinear(q.get("ref", ""))
                return self._send(data, 200 if data else 404)
            if u.path == "/context":
                if hasattr(query, "context"):
                    args = {"ref": q.get("ref", "")}
                    if not API_KEY:
                        args["user_id"] = None
                    data = query.context(**args)
                    return self._send(data, 200 if data else 404)
                return self._send({"error": "not available"}, 501)
            if u.path == "/language":
                data = query.language(q.get("ref", ""))
                return self._send(data, 200 if data else 404)
            if u.path == "/purpose":
                data = query.purpose(q.get("ref", ""))
                return self._send(data, 200 if data else 404)
            if u.path == "/chunks":
                data = query.chunks(q.get("ref", ""))
                return self._send(data, 200 if data else 404)
            if u.path == "/crossref":
                return self._send(query.crossrefs(q.get("ref", ""), limit=int(q.get("limit", 30))))
            if u.path == "/search":
                return self._send(query.search(q.get("q", ""), limit=int(q.get("limit", 20)),
                                               testament=q.get("testament"), book=q.get("book"),
                                               translation=q.get("translation")))
            if u.path == "/word":
                return self._send(query.word_lookup(q.get("q", ""), limit=int(q.get("limit", 30))))
            if u.path == "/topic":
                return self._send(query.topic_search(q.get("q", "")))
            if u.path == "/commentary":
                return self._send(query.commentary(q.get("ref", "")))
            if u.path == "/overlap":
                return self._send(query.book_overlap(q.get("book", ""), limit=int(q.get("limit", 15))))
            if u.path == "/character":
                return self._send(query.character_search(q.get("q", ""), limit=int(q.get("limit", 20))))
            if u.path == "/ancient":
                v = query.get_verse(q.get("ref", ""))
                return self._send((v or {}).get("ancient_versions", []))
            if u.path == "/sefaria":
                from . import sefaria
                return self._send(sefaria.fetch_verse(q.get("ref", "")), cache=False)
            if u.path == "/semantic":
                # Vector search; disabled until the host ships verse_vectors.db
                return self._send(query.semantic_search(q.get("q", ""),
                                                        limit=int(q.get("limit", 15)),
                                                        testament=q.get("testament"),
                                                        book=q.get("book")), cache=False)
            if u.path == "/graph_neighbors":
                return self._send(query.graph_neighbors(ref=q.get("ref"), q=q.get("q"),
                                                        limit=int(q.get("limit", 10))), cache=False)
            if u.path == "/books":
                return self._send(query.books())
            if u.path == "/sources":
                return self._send(query.sources())
            if u.path == "/random":
                return self._send(query.random_verse() or {}, cache=False)
            if u.path == "/stats":
                return self._send(query.stats())
            if u.path == "/doctor":
                return self._send(query.doctor(), cache=False)
            if u.path == "/health":
                return self._send({"ok": True, "one_api": "scripture + graph + semantic (semantic is Pro-compute route)"}, cache=False)
            return self._send({"error": "not found"}, 404)
        except ValueError as exc:
            return self._send({"error": str(exc)}, 400)
        except sqlite3.Error as exc:
            return self._send({"error": f"db: {exc}"}, 500)
        except Exception as exc:
            return self._send({"error": str(exc)}, 500)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        """MCP streamable HTTP transport (stateless JSON-RPC over POST)."""
        if not self._authed():
            return self._send({"error": "unauthorized"}, 401, cache=False)
        u = urlparse(self.path)
        if u.path != "/mcp":
            return self._send({"error": "not found"}, 404, cache=False)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return self._send({"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32700, "message": "empty body"}}, 400, cache=False)
        if length > 1_000_000:
            return self._send({"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32600, "message": "body too large"}}, 413, cache=False)
        try:
            msg = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self._send({"jsonrpc": "2.0", "id": None,
                               "error": {"code": -32700, "message": "parse error"}}, 400, cache=False)

        from . import mcp
        if isinstance(msg, list):
            out = [r for r in (self._mcp_dispatch(mcp, m) for m in msg) if r is not None]
            if not out:
                return self._accepted()
            return self._send(out, cache=False)
        out = self._mcp_dispatch(mcp, msg)
        if out is None:
            return self._accepted()
        return self._send(out, cache=False)

    def _mcp_dispatch(self, mcp, msg):
        if not isinstance(msg, dict):
            return {"jsonrpc": "2.0", "id": None,
                    "error": {"code": -32600, "message": "invalid request"}}
        mid = msg.get("id")
        method = msg.get("method")
        params = msg.get("params") or {}
        if method == "tools/call" and params.get("name") in MCP_BLOCKED:
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32601, "message": "tool not available here"}}
        out = mcp.handle(msg)
        if method == "tools/list" and out and "result" in out:
            out["result"]["tools"] = [t for t in out["result"]["tools"]
                                      if t.get("name") not in MCP_BLOCKED]
        if method == "initialize" and out and "result" in out:
            out["result"]["capabilities"] = {"tools": {"listChanged": False},
                                             "prompts": {"listChanged": False}}
        return out

    def _accepted(self):
        self.send_response(202)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # quiet by default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Levi API (scripture-only) on http://{args.host}:{args.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()

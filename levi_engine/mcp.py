#!/usr/bin/env python3
"""Levi MCP server — newline-delimited JSON-RPC 2.0 over stdio.

No third-party dependencies. Add to an MCP client as:
  command: /path/to/levi
  args: ["mcp"]
"""
from __future__ import annotations

import json
import sys
import traceback

from . import __version__, query

INSTRUCTIONS = (
    "Levi is the Scripture beating heart: text, original languages, contexts, "
    "cross-references, topics, ancient witnesses. The verse reference is the signal. "
    "Personal memory (notebooks, study graphs, what a user has walked through) lives "
    "in Ritual — the extended brain — and is read through Ritual's own API when the "
    "user is in session. Keep the layers separate: what the text says, what the "
    "original language adds, what ancient witnesses show, what historical context "
    "suggests, what interpreters said. Never invent citations; label reconstruction "
    "and uncertainty. Use levi_context before teaching a passage, levi_interlinear "
    "for words, levi_crossref for trails, levi_doctor if a tool fails."
)


def _instructions() -> str:
    return INSTRUCTIONS


PROMPTS = [
    {
        "name": "study_passage",
        "description": "Study one passage in layers using Levi's evidence channels.",
        "arguments": [
            {"name": "ref", "description": "Bible reference, e.g. 'John 1:1'", "required": True},
            {"name": "question", "description": "Optional question to keep in view", "required": False},
        ],
    },
    {
        "name": "recall_notebook",
        "description": "Retrace scripture layers for a topic or passage; personal memory lives in Ritual and is read from Ritual's brain API in session.",
        "arguments": [
            {"name": "query", "description": "Topic, phrase, or question", "required": True},
        ],
    },
]

TOOLS = [
    {
        "name": "levi_verse",
        "description": "Get a Bible verse with every translation, original-language tokens, Strong's codes, morphology, glosses, language tags, cross-references, topics, and book context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Reference, e.g. 'John 3:16' or 'Rom 8:28-30'"},
                "translations": {"type": "array", "items": {"type": "string"}, "description": "Optional translation codes (KJV, ASV, NHEB, YLT, Darby, BBE, Vulgate)"},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "levi_interlinear",
        "description": "Word-by-word interlinear for a verse range: surface form, transliteration, Strong's, morphology, gloss, lexicon definition, semantic domains, and Aramaic bridge.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_search",
        "description": "Full-text search across KJV, Hebrew, Greek, and lexical glosses. Supports testament/book filters and alternate translations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
                "testament": {"type": "string", "enum": ["OT", "NT"]},
                "book": {"type": "string"},
                "translation": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "levi_word",
        "description": "Look up a Hebrew/Greek word by Strong's number or lemma. Returns lexicon entries (Strong's, TBESH/TBESG, SDBH, LSJ), semantic domains, and occurrences.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Strong's code (H7307, G3056) or lemma"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": ["query"],
        },
    },
    {
        "name": "levi_crossref",
        "description": "Cross-references for a verse, ranked by OpenBible community votes, with the linked verse text.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "limit": {"type": "integer", "default": 30}, "min_votes": {"type": "integer", "default": 0}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_context",
        "description": "Layered study page for a verse: book context, translations, original-language glosses, language tags, LXX, ancient versions, cross-references, topics, commentary, and related Sefirot notes. Quiet Markdown by default; set full=true for lexical definitions and more commentary, or format=json for structured data.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "full": {"type": "boolean", "default": False},
                "format": {"type": "string", "enum": ["markdown", "json"], "default": "markdown"},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "levi_language",
        "description": "Language profile for a verse: Hebrew/Aramaic/Greek tags, mixed-language notes, and token-level language data. Use for Daniel, Ezra, and Semitic words in the Gospels.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_commentary",
        "description": "Public-domain commentary for a verse (Calvin, F. B. Meyer). Sefaria commentary can be fetched separately.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_topic",
        "description": "Search Nave's Topical Bible and Torrey's Topical Textbook, or get topics for a verse.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "verse": {"type": "string"}, "limit": {"type": "integer", "default": 30}},
        },
    },
    {
        "name": "levi_chunks",
        "description": "Original-language chunks for a verse or chapter: sof pasuq for Hebrew/Aramaic, Greek clause/period for the New Testament.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_purpose",
        "description": "Language purpose/register for a verse or chapter: liturgical, official, common, or trade/administration, plus language and period.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_book_overlap",
        "description": "Books that overlap with a given book by shared cross-references, ranked by connection strength.",
        "inputSchema": {
            "type": "object",
            "properties": {"book": {"type": "string"}, "limit": {"type": "integer", "default": 15}},
            "required": ["book"],
        },
    },
    {
        "name": "levi_character",
        "description": "Search biblical characters/prosopography from TIPNR: name, Strong's code, description, and references.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
            "required": ["query"],
        },
    },
    {
        "name": "levi_ancient_versions",
        "description": "Peshitta (Syriac) and Targum (Aramaic) readings for a verse, aligned to the canonical verse ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
    },
    {
        "name": "levi_sefaria",
        "description": "Fetch and cache Jewish commentary (Rashi, Ibn Ezra, Ramban) from Sefaria for a Tanakh verse. Requires network on first use.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string"},
                "commentators": {"type": "array", "items": {"type": "string",
                    "enum": ["rashi", "ibn_ezra", "ramban"]}},
                "refresh": {"type": "boolean", "default": False},
            },
            "required": ["ref"],
        },
    },
    {
        "name": "levi_doctor",
        "description": "Check database integrity, FTS indexes, language coverage, Sefirot tables, and source registry.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "levi_overview",
        "description": "A calm first-look dashboard: health, counts, recent Sefirot notes, review queue, and next steps.",
        "inputSchema": {
            "type": "object",
            "properties": {"recent": {"type": "integer", "default": 5},
                           "review": {"type": "integer", "default": 5}},
        },
    },
    {
        "name": "levi_backup",
        "description": "Make a safe, quick-checked SQLite backup of Levi's database.",
        "inputSchema": {
            "type": "object",
            "properties": {"dir": {"type": "string"}, "keep": {"type": "integer", "default": 10}},
        },
    },
    {
        "name": "levi_stats",
        "description": "Database statistics and source inventory.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _text(obj) -> str:
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _call(name: str, args: dict) -> str:
    uid = None  # the brain lives in Ritual now
    if name == "levi_verse":
        v = query.get_verse(args["ref"], args.get("translations"))
        return _text(v or {"error": "not found"})
    if name == "levi_interlinear":
        return _text(query.interlinear(args["ref"]) or {"error": "not found"})
    if name == "levi_search":
        return _text(query.search(args["query"], limit=args.get("limit", 20),
                                  testament=args.get("testament"), book=args.get("book"),
                                  translation=args.get("translation")))
    if name == "levi_word":
        return _text(query.word_lookup(args["query"], limit=args.get("limit", 30)))
    if name == "levi_crossref":
        return _text(query.crossrefs(args["ref"], limit=args.get("limit", 30),
                                     min_votes=args.get("min_votes", 0)))
    if name == "levi_context":
        if args.get("format") == "json":
            return _text(query.context_json(args["ref"], full=bool(args.get("full")),
                                            user_id=uid))
        return _text(query.context_markdown(args["ref"], full=bool(args.get("full")),
                                            user_id=uid))
    if name == "levi_language":
        return _text(query.language(args["ref"]) or {"error": "not found"})
    if name == "levi_commentary":
        return _text(query.commentary(args["ref"], limit=args.get("limit", 20)))
    if name == "levi_topic":
        if args.get("verse"):
            return _text(query.topics_for(args["verse"]))
        return _text(query.topic_search(args.get("query", ""), limit=args.get("limit", 30)))
    if name == "levi_chunks":
        return _text(query.chunks(args["ref"]))
    if name == "levi_purpose":
        return _text(query.purpose(args["ref"]) or {"error": "not found"})
    if name == "levi_book_overlap":
        return _text(query.book_overlap(args["book"], limit=args.get("limit", 15)))
    if name == "levi_character":
        return _text(query.character_search(args["query"], limit=args.get("limit", 20)))
    if name == "levi_ancient_versions":
        v = query.get_verse(args["ref"])
        return _text((v or {}).get("ancient_versions", []))
    if name == "levi_sefaria":
        from . import sefaria
        return _text(sefaria.fetch_verse(
            args["ref"], args.get("commentators") or ("rashi", "ibn_ezra", "ramban"),
            refresh=args.get("refresh", False)))
    if name == "levi_doctor":
        return _text(query.doctor())
    if name == "levi_overview":
        return _text(query.overview(recent_limit=args.get("recent", 5),
                                    review_limit=args.get("review", 5), user_id=uid))
    if name == "levi_backup":
        from . import db
        return _text(db.backup(query.DB_PATH, dest_dir=args.get("dir"),
                               keep=args.get("keep", 10)))
    if name == "levi_stats":
        return _text(query.stats())
def handle(msg: dict):
    method = msg.get("method")
    mid = msg.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False},
                             "prompts": {"listChanged": False}},
            "serverInfo": {"name": "levi-monster", "version": __version__},
            "instructions": _instructions(),
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "prompts/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"prompts": PROMPTS}}
    if method == "prompts/get":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "study_passage":
            ref = str(args.get("ref", "")).strip()
            question = str(args.get("question", "")).strip()
            text = (
                f"Study {ref} with Levi.\n\n"
                "0. Read the passage first. If a session token for Ritual's brain API is "
                "provided, you may consult the user's study memory there — never invent or "
                "assume personal details. Never ask for a key or token.\n"
                "1. Call `levi_context` for the passage. Read the text first.\n"
                "2. Use `levi_interlinear`, `levi_language`, and `levi_word` only where they add "
                "something real. Do not force a word study.\n"
                "3. Compare ancient witnesses with `levi_ancient_versions`; label reconstruction "
                "and translation.\n"
                "4. Use `levi_crossref` and `levi_topic` for context, then `levi_commentary` for "
                "later interpretation. Keep commentary separate from the text.\n"
                "5. Call `levi_crossref` for the strongest Bible cross-references and "
                "`levi_topic` for the thematic neighborhood. The verse text is the anchor; "
                "every layer hangs from it.\n"
                "6. Answer in layers and name uncertainty. Never invent a citation.\n"
            )
            if question:
                text += f"\nQuestion to keep in view: {question}\n"
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "description": "Layered study of one passage",
                "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
            }}
        if name == "recall_notebook":
            query_text = str(args.get("query", "")).strip()
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "description": "Recall and retrace Levi's notebook",
                "messages": [{"role": "user", "content": {"type": "text", "text": (
                    f"Retrace scripture layers for: {query_text}\n\n"
                    "Search the text with `levi_search`, then call `levi_crossref` for trails and "
                    "`levi_topic` for the thematic neighborhood. If the user gave a Bible "
                    "reference, begin with `levi_context` and report what the text itself says. "
                    "Personal study memory, when available, comes from Ritual's brain API with "
                    "the session — never invented, never assumed."
                )}}],
            }}
        return {"jsonrpc": "2.0", "id": mid,
                "error": {"code": -32602, "message": f"Unknown prompt: {name}"}}
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            text = _call(name, args)
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": text}], "isError": False}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}}
    if method in ("shutdown", "exit"):
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        try:
            out = handle(msg)
            if out is not None:
                sys.stdout.write(json.dumps(out, ensure_ascii=False, default=str) + "\n")
                sys.stdout.flush()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            if "id" in msg:
                sys.stdout.write(json.dumps({
                    "jsonrpc": "2.0", "id": msg.get("id"),
                    "error": {"code": -32603, "message": "internal error"}}) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()

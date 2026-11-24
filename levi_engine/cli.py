"""Levi Monster CLI.

Usage:
  python3 -m levi_engine.cli verse "John 3:16"
  python3 -m levi_engine.cli search "living water" --limit 10
  python3 -m levi_engine.cli word H7307
  python3 -m levi_engine.cli context "Romans 8:28" --full
  python3 -m levi_engine.cli ask "What does it mean to be born again?"
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import textwrap
import urllib.request

from . import query
from .config import DB_PATH, parse_ref


def _print_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _ref_or_die(ref):
    p = parse_ref(ref)
    if not p:
        print(f"Could not parse reference: {ref}", file=sys.stderr)
        sys.exit(2)
    return p


def cmd_stats(args):
    s = query.stats()
    if args.json:
        _print_json(s); return
    print("Levi Monster — database")
    print(f"  {s['database']}  ({s['size_mb']} MB)")
    for k, v in s.items():
        if k in ("database", "size_mb"):
            continue
        print(f"  {k:16} {v:>10,}")


def cmd_verse(args):
    v = query.get_verse(args.ref, args.translation)
    if not v:
        print(f"Not found: {args.ref}", file=sys.stderr); sys.exit(1)
    if args.json:
        _print_json(v); return
    print(f"\n{v['reference']}  [{v.get('lang','')}]")
    if v.get("lang_note"):
        print(f"  language note: {v['lang_note']}")
    print()
    for t in v["translations"]:
        print(f"{t['translation']:>10}: {t['text']}")
    if v.get("hebrew"):
        print(f"\nHebrew: {v['hebrew']}")
    if v.get("greek"):
        print(f"Greek:  {v['greek']}")
    if v.get("words"):
        print("\nOriginal tokens:")
        for w in v["words"]:
            lex = w.get("lexicon") or {}
            dom = f"  [{', '.join(w.get('domains', []))}]" if w.get("domains") else ""
            print(f"  {w['pos']:>2}. {w.get('surface','')} ({w.get('translit','')}) "
                  f"{w.get('strongs','')} {w.get('morph','')} — {w.get('gloss','')}{dom}")
            if args.defs and lex.get("definition"):
                for line in textwrap.wrap(lex["definition"], 110):
                    print(f"      {line}")
            if w.get("aramaic"):
                for a in w["aramaic"]:
                    print(f"      Aramaic: {a['aramaic']} ({a['translit']}) = {a['gloss']} [{a['confidence']}]")
    if v.get("purpose"):
        p = v["purpose"]
        print(f"\nRegister: {p.get('purpose')} / {p.get('language')} ({p.get('period')})")
        print(f"  {p.get('note','')} [{p.get('confidence','')}]")
    if v.get("ancient_versions"):
        print("\nAncient versions:")
        for a in v["ancient_versions"]:
            print(f"  {a['version']}: {a['text'][:180]}")
    if v["language_tags"]:
        print("\nLanguage tags:")
        for t in v["language_tags"]:
            print(f"  - {t['lang']} ({t['scope']}): {t.get('note','')}")
    if v["cross_refs"]:
        print("\nCross refs:")
        for x in v["cross_refs"][:10]:
            print(f"  {x.get('book','')} {x.get('chapter','')}:{x.get('verse','')} "
                  f"({x.get('votes',0)}) — {(x.get('kjv_text') or '')[:90]}")
    if v["topics"]:
        print("\nTopics: " + "; ".join(t["topic"] for t in v["topics"][:12]))
    if v.get("book_context"):
        bc = v["book_context"]
        print(f"\nBook: {bc['summary']}")
        print(f"  Genre: {bc['genre']} | Register: {bc['register']}")
    if v.get("book_overlap"):
        print("\nRelated books: " + ", ".join(f"{x['related_book']} ({x['score']})" for x in v["book_overlap"][:6]))
    if v.get("variants"):
        print(f"\nTextual/spelling variants: {len(v['variants'])} token records")


def cmd_chapter(args):
    ch = query.get_chapter(args.book, args.chapter)
    if "error" in ch:
        print(ch["error"], file=sys.stderr); sys.exit(1)
    if args.json:
        _print_json(ch); return
    print(f"\n{ch['book']} {ch['chapter']}")
    if ch.get("book_context"):
        print(f"{ch['book_context']['summary']}\n")
    for v in ch["verses"]:
        print(f"{v['verse']:>3}  {v['kjv_text']}")
        if v.get("hebrew"):
            print(f"     {v['hebrew']}")


def cmd_interlinear(args):
    data = query.interlinear(args.ref)
    if not data:
        print(f"Not found: {args.ref}", file=sys.stderr); sys.exit(1)
    if args.json:
        _print_json(data); return
    for v in data["verses"]:
        print(f"\n{v['reference']}  {v.get('kjv_text','')}")
        print(f"{'#':>3} {'surface':<22} {'translit':<20} {'strong':<10} {'morph':<16} gloss")
        for w in v["words"]:
            print(f"{w['pos']:>3} {(w.get('surface') or '')[:22]:<22} "
                  f"{(w.get('translit') or '')[:20]:<20} {(w.get('strongs') or ''):<10} "
                  f"{(w.get('morph') or '')[:16]:<16} {w.get('gloss','')}")
            for a in w.get("aramaic") or []:
                print(f"      ↳ Aramaic: {a['aramaic']} ({a['translit']}) = {a['gloss']} [{a['confidence']}]")


def cmd_word(args):
    data = query.word_lookup(args.query, limit=args.limit)
    if args.json:
        _print_json(data); return
    print(f"\nWord: {args.query}   Strong's: {', '.join(data['strongs']) or '—'}   occurrences: {data['count']}")
    for lex in data["lexicon"]:
        print(f"\n[{lex['strongs']}] {lex.get('lemma','')} ({lex.get('translit','')}) — {lex.get('gloss','')}")
        print(f"  source: {lex['source']}")
        if lex.get("definition"):
            for line in textwrap.wrap(lex["definition"], 110):
                print(f"  {line}")
    if data["domains"]:
        print("\nSemantic domains: " + "; ".join(sorted({d['label'] for d in data['domains']})))
    if data["occurrences"]:
        print("\nFirst occurrences:")
        for o in data["occurrences"][:args.limit]:
            print(f"  {o['book']} {o['chapter']}:{o['verse']} — {o['surface']} ({o['gloss']})")


def cmd_search(args):
    rows = query.search(args.query, limit=args.limit, testament=args.testament,
                        book=args.book, translation=args.translation)
    if args.json:
        _print_json(rows); return
    if not rows:
        print("No results.")
        return
    for r in rows:
        if "error" in r:
            print(r["error"]); continue
        text = r.get("snippet") or r.get("matched_text") or r.get("kjv_text") or ""
        print(f"{r['book']} {r['chapter']}:{r['verse']}  {text}")


def cmd_crossref(args):
    rows = query.crossrefs(args.ref, limit=args.limit, min_votes=args.min_votes)
    if args.json:
        _print_json(rows); return
    for x in rows:
        print(f"{x.get('book','')} {x.get('chapter','')}:{x.get('verse','')} "
              f"(votes {x.get('votes',0)}) — {(x.get('kjv_text') or '')[:120]}")


def cmd_topic(args):
    rows = query.topics_for(args.verse) if args.verse else query.topic_search(args.query, limit=args.limit)
    if args.json:
        _print_json(rows); return
    for t in rows:
        print(f"{t['topic']} [{t['source']}] {t.get('verse_id','')} — {t.get('entry','')}")


def cmd_commentary(args):
    rows = query.commentary(args.ref, limit=args.limit)
    if args.json:
        _print_json(rows); return
    for c in rows:
        print(f"\n=== {c['author']} — {c['work']} ===")
        print(c["text"])


def cmd_lang(args):
    data = query.language(args.ref)
    if not data:
        print("Not found", file=sys.stderr); sys.exit(1)
    if args.json:
        _print_json(data); return
    print(f"{data['book']} {data['chapter']}:{data['verse']}  lang={data['lang']}")
    if data.get("lang_note"):
        print(f"  note: {data['lang_note']}")
    for t in data["tags"]:
        print(f"  tag: {t['lang']} / {t['scope']} — {t.get('note','')}")
    for w in data["words"]:
        print(f"  {w['pos']:>3} {w['lang']:<3} {w.get('surface','')[:22]:<22} {w.get('strongs','')} {w.get('morph','')}")


def cmd_context(args):
    if getattr(args, "online", False):
        from . import sefaria
        status = sefaria.fetch_verse(args.ref)
        if not args.json:
            print(f"[Sefaria: {status}]", file=sys.stderr)
    uid = _current_uid()
    if args.json:
        print(query.context_json(args.ref, full=args.full, user_id=uid))
    else:
        print(query.context_markdown(args.ref, full=args.full, user_id=uid))


def _ollama(model, prompt, url):
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode())
    return data.get("response", "")


def cmd_ask(args):
    # Retrieval: direct scripture search. The brain lives in Ritual now.
    uid = None
    hits = query.search(args.question, limit=args.n)
    context_parts = []
    for h in hits[: args.n]:
        if "error" in h:
            continue
        ref = f"{h['book']} {h['chapter']}:{h['verse']}"
        context_parts.append(query.context_markdown(ref, full=False, user_id=uid))
    context = "\n\n---\n\n".join(context_parts)
    prompt = (
        "You are Levi, a Bible-study retrieval-and-synthesis engine. Answer only from the "
        "provided sources. Distinguish what the text says, what the original languages add, "
        "what the historical/cultural context suggests, and what is later interpretation. "
        "Flag uncertainty. Do not invent citations.\n\n"
        f"QUESTION: {args.question}\n\nSOURCES:\n{context}"
    )
    if args.context_only:
        print(prompt); return
    try:
        answer = _ollama(args.model, prompt, args.ollama_url)
        print(answer)
    except Exception as exc:
        print(f"No local model answered ({exc}).", file=sys.stderr)
        print("Showing the retrieved study bundle instead. "
              "Use --context-only to skip the model next time.", file=sys.stderr)
        print()
        print(context)


def cmd_chunks(args):
    rows = query.chunks(args.ref)
    if args.json:
        _print_json(rows); return
    for r in rows:
        print(f"[{r['kind']}] {r['label']}")
        print(f"  {r['text'][:500]}")


def cmd_purpose(args):
    p = query.purpose(args.ref)
    if not p:
        print("No purpose data.", file=sys.stderr); sys.exit(1)
    if args.json:
        _print_json(p); return
    print(f"{args.ref}: {p['purpose']} / {p['language']} / {p['period']}")
    print(f"  {p['note']} ({p['confidence']})")


def cmd_overlap(args):
    rows = query.book_overlap(args.book, limit=args.limit)
    if args.json:
        _print_json(rows); return
    for r in rows:
        print(f"{r['related_book']:<18} {r['score']:>6}  {r['basis']}")


def cmd_character(args):
    rows = query.character_search(args.query, limit=args.limit)
    if args.json:
        _print_json(rows); return
    for r in rows:
        print(f"{r['name']} [{r['strongs']}] — {r['description'][:220]}")
        print(f"  refs: {r['refs'][:220]}")


def cmd_sefaria(args):
    from . import sefaria
    if args.preload_torah:
        print(sefaria.preload_torah())
        return
    if args.targum:
        p = parse_ref(args.ref)
        if not p:
            print("Cannot parse ref", file=sys.stderr); sys.exit(1)
        print(sefaria.fetch_targum_chapter(p["book"], p["chapter"], refresh=args.refresh))
        return
    commentators = []
    if args.all:
        commentators = ["rashi", "ibn_ezra", "ramban"]
    else:
        if args.rashi:
            commentators.append("rashi")
        if args.ibn_ezra:
            commentators.append("ibn_ezra")
        if args.ramban:
            commentators.append("ramban")
    if not commentators:
        commentators = ["rashi"]
    status = sefaria.fetch_verse(args.ref, commentators, refresh=args.refresh)
    if args.json:
        _print_json(status); return
    print(status)
    for c in sefaria.cached_commentary(args.ref):
        print(f"\n=== {c['author']} — {c['work']} ===")
        print(c["text"][:8000])


def cmd_sources(args):
    rows = query.sources()
    if args.json:
        _print_json(rows); return
    for s in rows:
        print(f"{s['name']:<28} {s['kind']:<18} {s['status']:<12} {s['license']}")


def cmd_books(args):
    rows = query.books()
    if args.json:
        _print_json(rows); return
    for b in rows:
        print(f"{b['book']:<16} {b['genre'][:38]:<38} {b['register']}")


def cmd_random(args):
    v = query.random_verse()
    if v:
        print(f"{v['reference']} — {v.get('kjv_text','')}")


def cmd_overview(args):
    data = query.overview(recent_limit=args.recent, review_limit=args.review)
    if args.json:
        _print_json(data); return
    if not data.get("ok") and data.get("error"):
        print(f"Levi is not ready: {data['error']}", file=sys.stderr)
        for step in data.get("next") or []:
            print(f"  {step}")
        sys.exit(1)
    db = data.get("database") or {}
    counts = data.get("counts") or {}
    health = data.get("health") or {}
    sf = {}
    user = data.get("user") or {}
    print("Levi Monster")
    print(f"  {data.get('tagline', '')}")
    if user.get("id"):
        print(f"  user      {user.get('display_name')} ({user.get('id')}) "
              f"via {user.get('resolved_by')}")
    print(f"  database  {db.get('path', '')}  ({db.get('size_mb', 0)} MB)")
    print(f"  health    {health.get('summary', 'unknown')}")
    print("  text      " + ", ".join(
        f"{k.replace('_', ' ')}={v:,}" for k, v in counts.items()
        if k in ("verses", "words", "cross_refs", "commentary")
    ))
    print(f"  notebook  {sf.get('threads', 0)} study threads, "
          f"{sf.get('sections', 0)} sections, {sf.get('nodes', 0)} entries, "
          f"{sf.get('ref_occurrences', 0)} indexed refs, "
          f"{sf.get('links', 0)} personal links")
    recent = []
    recent_threads = data.get("recent_threads") or []
    if recent_threads:
        print("\nStudy threads")
        for n in recent_threads:
            print(f"  #{n['id']} {n['title']}  "
                  f"({n.get('section_count',0)} sections, {n.get('ref_count',0)} refs)")
    if recent:
        print("\nRecent notebook")
        for n in recent:
            refs = ", ".join(n.get("ref_labels") or [])
            thread = n.get("thread")
            suffix = f"  in {thread['title']}" if thread and thread.get("id") != n["id"] else ""
            print(f"  #{n['id']} {n['title']}{suffix}" + (f"  ({refs})" if refs else ""))
    review = (data.get("review") or {}).get("notes") or []
    if review:
        print("\nWorth a fresh look")
        for n in review[:args.review]:
            why = "; ".join(n.get("review_why") or [])
            print(f"  #{n['id']} {n['title']} — {why}")
    print("\nStart here")
    for step in data.get("next") or []:
        print(f"  {step}")


def cmd_backup(args):
    from . import db
    try:
        result = db.backup(query.DB_PATH, dest_dir=args.dir, keep=args.keep)
    except Exception as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        _print_json(result); return
    print(f"Backup: {result['path']}")
    print(f"  size: {result['size_mb']} MB")
    print(f"  quick_check: {result['quick_check']}")
    if result.get("removed"):
        print(f"  removed {len(result['removed'])} old backup(s)")
    if not result.get("ok"):
        sys.exit(1)


def cmd_restore(args):
    from . import db
    if not args.yes:
        print("Refusing to replace a database without confirmation.", file=sys.stderr)
        print(f"  current: {query.DB_PATH}", file=sys.stderr)
        print(f"  backup:  {args.backup}", file=sys.stderr)
        print("Stop other Levi processes, then run again with --yes. "
              "A safety snapshot is made first.", file=sys.stderr)
        sys.exit(2)
    try:
        result = db.restore(args.backup, db_path=query.DB_PATH,
                            safety_dir=args.safety_dir, keep=args.keep)
    except Exception as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        _print_json(result); return
    print(f"Restored: {result['path']}")
    print(f"  from: {result['source']}")
    print(f"  quick_check: {result['quick_check']}")
    if result.get("safety_backup"):
        print(f"  safety snapshot: {result['safety_backup']['path']}")
    if not result.get("ok"):
        sys.exit(1)


# ── Sefirot: notebook + personal cross-reference graph ───────────────

def cmd_doctor(args):
    result = query.doctor()
    if args.json:
        _print_json(result); return
    print("Levi doctor")
    for c in result["checks"]:
        mark = "ok" if c["ok"] else c["level"].upper()
        print(f"  [{mark:5}] {c['check']:20} {c['detail']}")
    print(f"\n{result['summary']}")
    if not result["ok"]:
        sys.exit(1)


def build_parser():
    parser = argparse.ArgumentParser(prog="levi", description="Levi Monster — AI Bible study engine",
                                     epilog="Run with no command for a calm overview.")
    parser.add_argument("--db", default=None, help="database path")
    sub = parser.add_subparsers(dest="cmd")

    s = sub.add_parser("build", help="build/update the database")
    s.add_argument("--reset", action="store_true")
    s.add_argument("--only", default="")

    s = sub.add_parser("stats"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_stats)
    s = sub.add_parser("verse"); s.add_argument("ref"); s.add_argument("--translation", action="append")
    s.add_argument("--defs", action="store_true"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_verse)
    s = sub.add_parser("chapter"); s.add_argument("book"); s.add_argument("chapter", type=int)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_chapter)
    s = sub.add_parser("interlinear"); s.add_argument("ref"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_interlinear)
    s = sub.add_parser("word"); s.add_argument("query"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_word)
    s = sub.add_parser("search"); s.add_argument("query"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--testament"); s.add_argument("--book"); s.add_argument("--translation")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_search)
    s = sub.add_parser("crossref"); s.add_argument("ref"); s.add_argument("--limit", type=int, default=30)
    s.add_argument("--min-votes", type=int, default=0); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_crossref)
    s = sub.add_parser("topic"); s.add_argument("query", nargs="?"); s.add_argument("--verse")
    s.add_argument("--limit", type=int, default=30); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_topic)
    s = sub.add_parser("commentary"); s.add_argument("ref"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_commentary)
    s = sub.add_parser("lang"); s.add_argument("ref"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_lang)
    s = sub.add_parser("context"); s.add_argument("ref"); s.add_argument("--full", action="store_true")
    s.add_argument("--online", action="store_true", help="fetch Sefaria commentary first")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_context)
    s = sub.add_parser("ask"); s.add_argument("question"); s.add_argument("--n", type=int, default=6)
    s.add_argument("--model", default=os.environ.get("LEVI_MODEL", "qwen2.5:14b"))
    s.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    s.add_argument("--context-only", action="store_true"); s.set_defaults(fn=cmd_ask)
    s = sub.add_parser("sources"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_sources)
    s = sub.add_parser("books"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_books)
    s = sub.add_parser("purpose"); s.add_argument("ref"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_purpose)
    s = sub.add_parser("chunks"); s.add_argument("ref"); s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_chunks)
    s = sub.add_parser("overlap"); s.add_argument("book"); s.add_argument("--limit", type=int, default=15)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_overlap)
    s = sub.add_parser("character"); s.add_argument("query"); s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_character)
    s = sub.add_parser("sefaria", help="fetch/cache Rashi, Ibn Ezra, Ramban, Targum")
    s.add_argument("ref", nargs="?", default="")
    s.add_argument("--rashi", action="store_true")
    s.add_argument("--ibn-ezra", action="store_true")
    s.add_argument("--ramban", action="store_true")
    s.add_argument("--all", action="store_true")
    s.add_argument("--targum", action="store_true")
    s.add_argument("--preload-torah", action="store_true")
    s.add_argument("--refresh", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_sefaria)
    s = sub.add_parser("random"); s.set_defaults(fn=cmd_random)
    s.add_argument("--tag", default=""); s.set_defaults(fn=cmd_note)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_notes)
    s = sub.add_parser("doctor", help="check database and channel integrity")
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_doctor)
    s = sub.add_parser("overview", help="show a calm first-look dashboard")
    s.add_argument("--recent", type=int, default=5)
    s.add_argument("--review", type=int, default=5)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_overview)
    s = sub.add_parser("backup", help="make a safe, checked SQLite backup")
    s.add_argument("--dir", default=None)
    s.add_argument("--keep", type=int, default=10)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_backup)
    s = sub.add_parser("restore", help="restore a checked backup (offline; asks first)")
    s.add_argument("backup")
    s.add_argument("--yes", action="store_true")
    s.add_argument("--safety-dir", default=None)
    s.add_argument("--keep", type=int, default=10)
    s.add_argument("--json", action="store_true"); s.set_defaults(fn=cmd_restore)

    s = sub.add_parser("mcp", help="run the MCP stdio server")
    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--port", type=int, default=8777)
    s.add_argument("--host", default="127.0.0.1")

    return parser


def _run_command(args):
    if args.cmd == "build":
        from .ingest import main as build_main
        build_args = []
        if getattr(args, "db", None):
            build_args += ["--db", args.db]
        build_args += (["--reset"] if args.reset else [])
        build_args += (["--only", args.only] if args.only else [])
        build_main(build_args)
    elif args.cmd == "mcp":
        from .mcp import main as mcp_main
        mcp_main()
    elif args.cmd == "serve":
        sys.argv = ["levi-api", "--port", str(args.port), "--host", args.host]
        from .api import main as api_main
        api_main()
    else:
        args.fn(args)


def main(argv=None):
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)
    if getattr(args, "db", None):
        os.environ["LEVI_DB_PATH"] = args.db
        from . import config, query as q
        config.DB_PATH = args.db
        q.DB_PATH = args.db
        q._conn = None
    if not args.cmd:
        args.cmd = "overview"
        args.recent = 5
        args.review = 5
        args.json = False
        args.fn = cmd_overview
    try:
        _run_command(args)
    except BrokenPipeError:
        raise SystemExit(0)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        if os.environ.get("LEVI_DEBUG"):
            raise
        print(f"Levi: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

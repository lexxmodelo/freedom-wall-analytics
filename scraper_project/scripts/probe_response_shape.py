"""Capture one /api/graphql/ response and report the JSON paths where
`message.text` and `creation_time` live, to diagnose why most posts have
no timestamps.

Usage (from project root):
    python scripts/probe_response_shape.py
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJ = os.path.dirname(_HERE)
if _PROJ not in sys.path:
    sys.path.insert(0, _PROJ)

from config import ScraperConfig, TARGETS
from scraper import FacebookScraper, _GraphQLPostExtractor
from graphql_httpx import harvest_tokens, close_session


def find_paths(node, key_target, path=()):
    """DFS yielding (path, value) for every occurrence of `key_target`."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key_target:
                yield path + (k,), v
            yield from find_paths(v, key_target, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from find_paths(v, key_target, path + (f"[{i}]",))


def main() -> int:
    cfg = ScraperConfig(
        cookie_file=os.path.join(_PROJ, "cookies.json"),
        headless=True,
    )
    scraper = FacebookScraper(cfg)
    if not scraper._cookies:
        print("[error] no cookies; run extract_cookies.py first")
        return 1

    target = next(t for t in TARGETS if t["code"] == "SLU")
    print("[probe] harvesting one pagination request...")
    tokens = harvest_tokens(scraper, cfg, "SLU", target["url"])
    if not tokens:
        print("[error] harvest failed")
        return 1
    try:
        # Replay once to get a parseable response.
        api = tokens.context.request
        resp = api.post(
            tokens.url,
            data=tokens.raw_body,
            headers={**tokens.headers,
                     "content-type": "application/x-www-form-urlencoded"},
            timeout=30000,
        )
        body = resp.body() or b""
        if body.startswith(b"for (;;);"):
            body = body[len(b"for (;;);"):]

        out = os.path.join(_HERE, "_probe_response.json")
        with open(out, "wb") as f:
            f.write(body)
        print(f"[probe] saved response: {out} ({len(body)} bytes)")

        chunks = list(_GraphQLPostExtractor._iter_json_chunks(body))
        print(f"[probe] parsed {len(chunks)} chunks")

        # Aggregate paths across chunks.
        msg_paths = []
        ct_paths = []
        for chunk in chunks:
            for p, v in find_paths(chunk, "message"):
                if isinstance(v, dict) and isinstance(v.get("text"), str):
                    msg_paths.append((p, len(v["text"])))
            for p, v in find_paths(chunk, "creation_time"):
                ct_paths.append((p, v))

        print()
        print(f"== {len(msg_paths)} message.text occurrences ==")
        for p, ln in msg_paths[:8]:
            print(f"  /{'/'.join(p)}  (text len={ln})")

        print()
        print(f"== {len(ct_paths)} creation_time occurrences ==")
        for p, v in ct_paths[:8]:
            print(f"  /{'/'.join(p)}  = {v}")

        # For each message path, find the nearest creation_time ancestor.
        print()
        print("== message → nearest creation_time ancestor ==")
        ct_path_set = {tuple(p) for p, _ in ct_paths}
        for mpath, _ in msg_paths[:6]:
            # message lives at .../message; we want the ancestor of .../message
            # that contains a creation_time.
            common_ancestors = []
            for cpath in ct_path_set:
                # cpath ends with "creation_time"; ancestor is cpath[:-1]
                ancestor = cpath[:-1]
                # Is ancestor a prefix of mpath?
                if len(ancestor) <= len(mpath) and \
                        tuple(mpath[:len(ancestor)]) == ancestor:
                    common_ancestors.append(ancestor)
            if common_ancestors:
                # Pick the longest (deepest) — closest to message
                best = max(common_ancestors, key=len)
                depth_diff = len(mpath) - len(best)
                print(f"  msg /{'/'.join(mpath)}")
                print(f"    nearest ct ancestor /{'/'.join(best)}/creation_time")
                print(f"    depth difference: {depth_diff}")
            else:
                print(f"  msg /{'/'.join(mpath)} — NO creation_time ancestor")

        return 0
    finally:
        close_session(tokens)


if __name__ == "__main__":
    sys.exit(main())

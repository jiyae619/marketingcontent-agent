#!/usr/bin/env python3
"""Validation fixture for local-model residency (providers._evict_others).

Dependency-free (stdlib assert), and it never touches a real Ollama: the HTTP
layer is stubbed, so this runs on a machine with no models loaded and costs
nothing. What it locks down is the invariant CLAUDE.md states and nothing
enforced until now — on an 8GB box the model about to run must be the ONLY
resident model.

Two of these cases are failure modes that would be invisible in production:
sparing nothing (a reload on every single call, silently ~4GB and seconds of
latency each time) and raising on a non-Ollama server (call_local is documented
to work against LM Studio / llama.cpp / vLLM, which have no /api/ps).

    Run:  python3 scripts/test_residency.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO_ROOT)

import providers  # noqa: E402

CHECKS = 0
BASE = "http://localhost:11434/v1"


def check(label, cond):
    global CHECKS
    assert cond, f"FAILED: {label}"
    CHECKS += 1
    print(f"  ok  {label}")


class Stub:
    """Stands in for Ollama: records unload calls, replays a fixed /api/ps."""

    def __init__(self, loaded, ps_raises=False, unload_raises=False):
        self.loaded = loaded
        self.ps_raises = ps_raises
        self.unload_raises = unload_raises
        self.unloaded = []

    def urlopen(self, req, timeout=None):
        if self.ps_raises:
            raise urllib.error.URLError("no /api/ps here")
        body = json.dumps({"models": [{"name": n} for n in self.loaded]}).encode()

        class R:
            def read(self_inner):
                return body

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

        return R()

    def post_json(self, url, payload, headers, timeout=60):
        assert payload.get("keep_alive") == 0, "unload must send keep_alive 0"
        assert "prompt" not in payload, "unload must not run the model"
        self.unloaded.append(payload["model"])
        if self.unload_raises:
            raise urllib.error.URLError("unload refused")
        return {"done_reason": "unload"}


def run(stub, keep, base=BASE):
    real_open, real_post = urllib.request.urlopen, providers._post_json
    urllib.request.urlopen = stub.urlopen
    providers._post_json = stub.post_json
    try:
        providers._evict_others(base, keep)
    finally:
        urllib.request.urlopen = real_open
        providers._post_json = real_post
    return stub


def main():
    print("\nR1 residency: the model about to run is the only survivor")

    s = run(Stub(["gemma3:4b", "llama3.2:3b"]), keep="gemma3:4b")
    check("the rival is unloaded", s.unloaded == ["llama3.2:3b"])

    # The expensive invisible bug: evicting your own model reloads ~4GB per call.
    s = run(Stub(["gemma3:4b"]), keep="gemma3:4b")
    check("the model in use is never unloaded", s.unloaded == [])

    s = run(Stub([]), keep="gemma3:4b")
    check("nothing loaded is a no-op", s.unloaded == [])

    s = run(Stub(["a:1", "b:2", "gemma3:4b"]), keep="gemma3:4b")
    check("every rival goes, not just the first", s.unloaded == ["a:1", "b:2"])

    print("\nR2 portability: a non-Ollama server keeps its own policy")

    s = run(Stub(["x:1"], ps_raises=True), keep="gemma3:4b")
    check("no /api/ps -> no unloads, no raise", s.unloaded == [])

    s = run(Stub(["a:1", "b:2"], unload_raises=True), keep="gemma3:4b")
    check("a failed unload still tries the rest", s.unloaded == ["a:1", "b:2"])

    print("\nR3 base URL forms")
    for form in ("http://h:11434/v1", "http://h:11434/v1/", "http://h:11434"):
        check(f"{form:24} -> http://h:11434",
              providers._ollama_root(form) == "http://h:11434")

    print(f"\nALL {CHECKS} CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n{e}")
        sys.exit(1)

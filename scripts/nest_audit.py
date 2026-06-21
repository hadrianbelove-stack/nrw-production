#!/usr/bin/env python3
"""Audit markdown docs for /nest candidates.

Finds, across the given docs:
  - inline ```python … python3 -c``` blocks (logic -> script candidates)
  - fenced code blocks that are duplicated across files (dup -> shared candidate)
  - large fenced blocks (bulky reference/template -> separate-file candidate)

Read-only. Prints a report; never edits.

Usage: nest_audit.py [glob ...]   (default: .claude/commands/*.md)
"""
import glob
import hashlib
import re
import sys

FENCE = re.compile(r"```.*?```", re.DOTALL)


def norm(block):
    # strip fences + collapse whitespace so trivially-different copies still match
    body = block.strip("`")
    body = re.sub(r"^[a-zA-Z0-9]*\n", "", body, count=1)  # drop language tag line
    return re.sub(r"\s+", " ", body).strip()


def main():
    paths = sys.argv[1:] or sorted(glob.glob(".claude/commands/*.md"))
    blocks = {}          # norm-hash -> {"sample": str, "lines": int, "files": set}
    py_inline = {}       # file -> count of python3 -c blocks
    big = []             # (lines, file, first_line) large fenced blocks

    for path in paths:
        text = open(path).read()
        py_inline[path] = text.count("python3 -c")
        for m in FENCE.finditer(text):
            block = m.group(0)
            n_lines = block.count("\n") + 1
            h = hashlib.md5(norm(block).encode()).hexdigest()
            rec = blocks.setdefault(h, {"sample": block, "lines": n_lines, "files": []})
            rec["files"].append(path)
            if n_lines >= 12 and "python3 -c" not in block:
                first = block.splitlines()[1][:60] if n_lines > 1 else ""
                big.append((n_lines, path, first))

    print("=== inline `python3 -c` blocks (logic -> script) ===")
    for path, n in sorted(py_inline.items(), key=lambda x: -x[1]):
        if n:
            print(f"  {n:2d}  {path}")

    print("\n=== fenced blocks duplicated across files (dup -> shared) ===")
    dups = [(len(set(r["files"])), r) for r in blocks.values() if len(set(r["files"])) > 1]
    for cnt, r in sorted(dups, key=lambda x: (-x[0], -x[1]["lines"])):
        files = ", ".join(sorted(set(r['files'])).__iter__())
        first = r["sample"].splitlines()
        label = (first[1] if len(first) > 1 else first[0])[:55]
        print(f"  x{cnt}  (~{r['lines']}L)  {label!r}")
        print(f"        in: {files}")

    print("\n=== large fenced blocks (bulky -> separate file) ===")
    for n_lines, path, first in sorted(big, reverse=True)[:20]:
        print(f"  {n_lines:3d}L  {path}  — {first!r}")


if __name__ == "__main__":
    main()

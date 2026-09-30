# Developer notes

This folder holds the project's working knowledge: the rules, traps and history that used to live in one very large `CLAUDE.md`. It exists so that `CLAUDE.md` can stay small (it is loaded into every Claude Code session) while nothing that was learned is lost.

Nothing in this folder is loaded automatically. Do not `@`-import any file from here into `CLAUDE.md`, and do not name a file here `CLAUDE.md` (Claude Code loads files with that name on its own).

## Layout

| Path | What it is | When to open it |
|---|---|---|
| `../../CLAUDE.md` | Universal rules and the "read this before working on that" index | Loaded every session |
| `guides/<topic>.md` | The distilled standing rules, traps, verification habits, operator commands, open follow-ups and flags for one area. Ends with a coverage table for its archive. | Before you change that area |
| `archive/<topic>.md` | The original release write-ups for that area, verbatim, in their original order. Each section is wrapped in `BEGIN` and `END` comments giving its line range in the untouched original. | When you need the reasoning, measurements or history behind a rule. Grep it, do not read it whole. |
| `archive/CLAUDE.original-2026-09-30.md` | Byte-for-byte copy of `CLAUDE.md` as it stood before the split (1,234,024 bytes, 17,096 lines, sha256 `b5f64986edb497190c55217bcb2508e65b459ca99fe72da38c8368cca089d09b`) | Only to settle a doubt about the split |
| `COVERAGE.md` | Checklist mapping every one of the 166 original sections to its archive file and guide, and mapping every code comment that says "see CLAUDE.md" to its new home | To find where an old section went |
| `FLAGS.md` | Conflicting, superseded or possibly obsolete guidance found during the split, with a recommended action | Before trusting an old rule that looks odd |

## Conventions

- **A guide is the source of truth for rules; the archive is the source of truth for history.** If they disagree, the code wins, and the guide should be fixed in the same change.
- **Adding a release note**: append the write-up to the end of the matching `archive/<topic>.md` (inside its own `BEGIN`/`END` markers if you want it to stay machine-checkable, or as a plain dated section). If it produced a rule that outlives the release, add one or two lines to the matching guide. Do not put release write-ups in `CLAUDE.md`.
- **Adding a topic**: create both `guides/<topic>.md` and `archive/<topic>.md`, add a row to the "Read this before working on that" table in `CLAUDE.md`, and a row to `COVERAGE.md`.
- **Resolving a flag**: edit the guide, then mark the entry resolved in `FLAGS.md` with the commit.
- **Voice**: plain Australian cricket-club voice, no em or en dashes, per the writing-voice rule in `CLAUDE.md`. Verbatim archive text keeps its original punctuation.

## Re-checking that the split lost nothing

The archive files reassemble to the original exactly. From the repo root:

```bash
python3 - <<'EOF'
import re, glob, hashlib
R = "docs/dev-notes/archive"
orig = open(f"{R}/CLAUDE.original-2026-09-30.md", "rb").read()
pre = orig.split(b"\n## ", 1)[0] + b"\n"
pieces = {}
for f in glob.glob(f"{R}/*.md"):
    if "CLAUDE.original" in f:
        continue
    for m in re.finditer(rb"<!-- BEGIN original CLAUDE\.md L(\d+)-(\d+) -->\n(.*?)<!-- END original CLAUDE\.md L\1-\2 -->\n", open(f, "rb").read(), re.S):
        pieces[int(m.group(1))] = m.group(3)
rebuilt = pre + b"".join(pieces[k] for k in sorted(pieces))
print(len(pieces), "sections;", "BYTE-IDENTICAL" if rebuilt == orig else "MISMATCH")
EOF
```

This only holds for the sections moved on 2026-09-30. Sections appended after that date are outside the markers' line ranges and are not part of the check.

## Sizes at the time of the split

See the "Before and after" table in `COVERAGE.md`.

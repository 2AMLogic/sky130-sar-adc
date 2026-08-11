#!/usr/bin/env bash
# check-xschem-embedded-quotes.sh - Fail if any tracked xschem .sch/.sym file
# has a `value="..."` (or other xschem quoted text-attribute, e.g.
# `author="..."`, `format="..."`) block containing an embedded literal `"`
# character.
#
# Why (#59): xschem's netlister terminates a quoted text-attribute string
# (`attr="..."`) at the FIRST literal `"` it encounters -- it does not
# respect nested or "intended" quoting. Anything past that first embedded `"`
# can be silently dropped from the netlisted output, with no warning at
# netlist time. This bit design/bandgap_core.sch (#54/#58): a `"Sizing
# rationale"` comment with literal double quotes inside a `code_shown.sym`
# `value="..."` block truncated the block mid-way, silently dropping several
# `.param` declarations. ngspice then failed with a confusing "Undefined
# parameter" error far from the actual root cause. This check catches the
# hazard at authoring time instead of at simulation time.
#
# What counts as an authoring convention (verified against every current
# quoted-attribute use in this repo, see design/README.md):
#   - Single-line: `attr="...single line..."` -- the value opens and closes
#     on the same line. Exactly one embedded `"` pair is expected (the
#     opening and the intended closing quote); a bare xschem parameter
#     substitution like 't_ramp' uses single quotes, so it never trips this.
#   - Multi-line (code_shown/code blocks): `value="` ends the opening line
#     with nothing after it, and the block is closed by a line whose first
#     non-whitespace character is the closing `"` (e.g. a bare `"}` line for
#     code_shown.sym, or a bare `"` line followed by more attributes like
#     `spice_ignore=false}` for code.sym) -- this convention holds for every
#     multi-line quoted-attribute block in the repo today, and matches how
#     xschem itself finds the terminator (the first `"` it sees, wherever it
#     falls). Any `"` character elsewhere on an intermediate line -- i.e. not
#     as that line's first non-whitespace character -- is an embedded literal
#     quote that truncates the block early.
#
# This intentionally does NOT try to be a general xschem-file parser: it
# checks the two shapes that occur in this repo's `.sch`/`.sym` files, which
# is sufficient to catch the class of hazard #59 reports (and is paired with
# the authoring-convention note in design/README.md so new schematics follow
# the same shape).
#
# Usage:
#   check-xschem-embedded-quotes.sh [ROOT]
#     ROOT  Repository root to scan tracked .sch/.sym files under. Defaults
#           to `git rev-parse --show-toplevel`, then the script's own repo
#           root.
#
# Exit codes: 0 = no embedded literal quotes found (or nothing to check);
# 1 = one or more quoted-attribute blocks contain an embedded literal `"`
#     (offenders named with file:line on stderr).

set -euo pipefail

# --- Resolve ROOT -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ROOT="$1"
else
  if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    :
  else
    # .loom/scripts/ -> .loom/ -> repo root
    ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
  fi
fi

# --- Collect tracked .sch/.sym files -----------------------------------------
mapfile -t FILES < <(git -C "$ROOT" ls-files '*.sch' '*.sym' 2>/dev/null || true)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "check-xschem-embedded-quotes: no tracked .sch/.sym files under $ROOT — nothing to check (ok)."
  exit 0
fi

found=0

for rel in "${FILES[@]}"; do
  file="$ROOT/$rel"
  [[ -f "$file" ]] || continue

  in_block=0
  block_start_line=0
  block_attr=""
  lineno=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    lineno=$((lineno + 1))

    if [[ "$in_block" -eq 1 ]]; then
      # A multi-line attr="..." block is closed by a line whose first
      # non-whitespace character is the closing " (matching how xschem
      # itself finds the terminator -- the first " it sees). Whatever
      # follows on that line (e.g. "}, or  spice_ignore=false}) is outer
      # attribute syntax, not value content, so it is not scanned further.
      # A " appearing anywhere else on an intermediate line is embedded
      # content that truncates the block early.
      if [[ "$line" =~ ^[[:space:]]*\" ]]; then
        in_block=0
        continue
      fi
      if [[ "$line" == *'"'* ]]; then
        echo "EMBEDDED QUOTE: ${rel}:${lineno}" >&2
        echo "  inside ${block_attr}=\"...\" block opened at ${rel}:${block_start_line}" >&2
        echo "  line: ${line}" >&2
        found=1
      fi
      continue
    fi

    # Not currently in a multi-line block: look for quoted-attribute
    # opening(s) on this line, e.g. value=", author=", format=" -- any bare
    # identifier followed by =" (there is normally at most one per line in
    # this repo).
    rest="$line"
    while [[ "$rest" =~ ([A-Za-z_][A-Za-z0-9_]*)=\" ]]; do
      attr="${BASH_REMATCH[1]}"
      match="${BASH_REMATCH[0]}"
      after="${rest#*"$match"}"
      # Consume this occurrence from `rest` so a second attr=" on the same
      # line (not seen today, but handled defensively) is scanned too.
      rest="$after"

      if [[ -z "$after" ]]; then
        # attr=" is the last thing on the line -> multi-line block opener.
        in_block=1
        block_start_line=$lineno
        block_attr="$attr"
        break
      fi

      # Single-line case: everything after the opening quote up to end of
      # line is the candidate value content. Exactly one embedded `"` is
      # expected (the intended closing quote); a second `"` means content
      # continues past what xschem will actually treat as the terminator.
      quote_count=$(grep -o '"' <<<"$after" | wc -l | tr -d '[:space:]')
      if [[ "$quote_count" -ge 2 ]]; then
        echo "EMBEDDED QUOTE: ${rel}:${lineno}" >&2
        echo "  ${attr}=\"...\" on this line closes at the first embedded \", but" >&2
        echo "  another literal \" follows on the same line -- content after the" >&2
        echo "  first \" is silently dropped by xschem's netlister." >&2
        echo "  line: ${line}" >&2
        found=1
      fi
    done
  done < "$file"

  if [[ "$in_block" -eq 1 ]]; then
    echo "check-xschem-embedded-quotes: WARNING — ${rel}: ${block_attr}=\"...\" block opened at line ${block_start_line} never closed with a bare \" line (unusual shape, please review manually)." >&2
  fi
done

if [[ "$found" -ne 0 ]]; then
  echo "" >&2
  echo "check-xschem-embedded-quotes: FAIL — one or more xschem quoted text-" >&2
  echo "attribute blocks (attr=\"...\") contain an embedded literal \" character. xschem's" >&2
  echo "netlister silently truncates the value at the FIRST such quote, dropping" >&2
  echo "everything after it (including any .param declarations) with no error." >&2
  echo "Remove or rework the embedded quotes (e.g. drop the surrounding \" \" or" >&2
  echo "use a different marker like emphasis/dashes) — see design/README.md." >&2
  exit 1
fi

echo "check-xschem-embedded-quotes: OK — no embedded literal quotes found in ${#FILES[@]} tracked .sch/.sym file(s)."
exit 0

#!/usr/bin/env bash
# NRW Bash permission guard (PreToolUse hook).
#
# Goal: the user (a non-coder Creative Director) should never have to click
# "yes" for everyday work, but commands that could permanently destroy movie
# data or rewrite git history should still PAUSE for a confirmation.
#
# Reads the PreToolUse hook JSON on stdin, inspects .tool_input.command, and
# prints a permissionDecision:
#   - "ask"   -> force the confirmation prompt (dangerous patterns below)
#   - "allow" -> auto-approve, no prompt (everything else)
#
# It only ever PAUSES; it never hard-blocks, so a genuinely-needed dangerous
# command can still be approved (with Claude's explanation, per CLAUDE.md).

input="$(cat)"
cmd="$(printf '%s' "$input" | /usr/bin/jq -r '.tool_input.command // ""')"
lc="$(printf '%s' "$cmd" | /usr/bin/tr '[:upper:]' '[:lower:]')"

ask() {
  /usr/bin/jq -n --arg r "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"ask",permissionDecisionReason:$r}}'
  exit 0
}
allow() {
  /usr/bin/jq -n \
    '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow"}}'
  exit 0
}
match() { printf '%s' "$lc" | /usr/bin/grep -qE "$1"; }

# 1. Full pipeline regeneration (expensive; can overwrite manual edits).
case "$lc" in
  *generate_data.py*--full*)
    ask "FULL pipeline regeneration (--full): expensive and can overwrite your manual edits. Approve only if you really mean to rebuild everything." ;;
esac

# 2. Direct destruction/overwrite of the data files (the pipeline should be the
#    only thing that writes these). Matches data.json / data_archive.json as the
#    target of a destructive verb or a redirect; ignores reads and .backup/.jsonl.
if match '(rm|mv|cp|truncate)[[:space:]][^|&;]*data(_archive)?\.json([^.0-9a-z]|$)' \
   || match '>[[:space:]]*data(_archive)?\.json([^.0-9a-z]|$)'; then
  ask "This writes over or deletes data.json / data_archive.json directly. Only the pipeline should change these files (CLAUDE.md hard rule)."
fi

# 3. Recursive deletes (rm -r / -rf / -fr): can wipe whole folders.
if match 'rm[[:space:]]+-[a-z]*r'; then
  ask "Recursive delete (rm -r...): this can wipe entire folders. Check the path before approving."
fi

# 4. Git history rewrites / force pushes / conflict-side checkouts / clean.
if match 'git[[:space:]]+push[^|&;]*(--force|[[:space:]]-f([[:space:]]|$))'; then
  ask "Force push: can overwrite work on the remote. Review before approving."
fi
if match 'git[[:space:]]+reset[[:space:]]+--hard'; then
  ask "git reset --hard: permanently discards local changes. Review before approving."
fi
if match 'git[[:space:]]+checkout[^|&;]*(--ours|--theirs)'; then
  ask "Conflict-side checkout (--ours/--theirs) can silently drop movie updates (CLAUDE.md). Review before approving."
fi
if match 'git[[:space:]]+clean[^|&;]*-[a-z]*f'; then
  ask "git clean -f: deletes untracked files, including uncommitted work. Review before approving."
fi

# 5. Privilege escalation.
if match '(^|[[:space:]])sudo([[:space:]]|$)'; then
  ask "sudo: runs with admin privileges. Review before approving."
fi

# Everyday command -> auto-approve, no prompt.
allow

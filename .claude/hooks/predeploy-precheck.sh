#!/bin/bash
# PreToolUse hook (Bash). Runs a frontend build check before letting a
# deploy-shaped command actually execute — git push, npm run build, or
# anything mentioning "deploy" — and DENIES the tool call if the build
# fails, showing the real error. The point is to stop a broken build from
# reaching `git push` (and from there, CI or a real deploy) in the first
# place, rather than finding out after the fact.
#
# Silent (no output = default permission handling applies) for every
# non-matching command, and for a matching command whose precheck build
# passes. Only speaks up to deny.
set -u

# Repo root = two levels up from this script's own location
# (<repo>/.claude/hooks/predeploy-precheck.sh), resolved from the script's
# path rather than hardcoded, so this file has no machine-specific path in
# it and is safe to commit as-is.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

cmd=$(jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0

# Case-insensitive substring match on the three named patterns. Not a strict
# command-boundary parse — a false positive just costs one extra build
# check (cheap, harmless); a false negative would let a broken build slip
# through, which is the exact failure this hook exists to catch, so the
# match stays deliberately loose.
lc_cmd=$(printf '%s' "$cmd" | tr '[:upper:]' '[:lower:]')
case "$lc_cmd" in
  *"git push"*|*"npm run build"*|*deploy*) ;;
  *) exit 0 ;;
esac

# Prefer client/ if this repo has a separate frontend directory (common in
# split client/server layouts); otherwise fall back to the repo root, which
# is where the frontend actually lives in THIS repo — there is no client/
# here, package.json sits at the repo root.
if [ -f "$REPO_ROOT/client/package.json" ]; then
  BUILD_DIR="$REPO_ROOT/client"
elif [ -f "$REPO_ROOT/package.json" ]; then
  BUILD_DIR="$REPO_ROOT"
else
  exit 0  # no package.json anywhere findable — nothing this hook can check
fi

cd "$BUILD_DIR" || exit 0
build_output=$(npm run build 2>&1)
build_rc=$?

if [ "$build_rc" -eq 0 ]; then
  exit 0
fi

# Deny the tool call and show why. Keep the TAIL of the output, not the
# head — a build failure's actual error is almost always the last thing
# printed (webpack/vite/tsc stack traces land at the bottom).
reason=$(printf '%s' "$build_output" | tail -c 4000)
jq -n \
  --arg cmd "$cmd" \
  --arg dir "$BUILD_DIR" \
  --arg out "$reason" \
  '{
    systemMessage: ("predeploy-precheck: npm run build failed in " + $dir + " — blocked: " + $cmd),
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "deny",
      permissionDecisionReason: ("npm run build failed in " + $dir + ":\n\n" + $out)
    }
  }'
exit 0

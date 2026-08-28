#!/bin/bash
# PostToolUse hook (Write|Edit). Runs tools/bughunt/bughunt.py --quick right after an
# edit to one of the core judge-pipeline files, so a regression this repo already got
# burned by once (judge != generator collapsing, an abstained verdict still carrying a
# score, ...) surfaces in the same turn instead of at the next push to CI.
#
# Silent on success and on any non-matching file — only speaks up when a check fails.
set -u

REPO_DIR="/Users/jiyaechoi/dev/marketingcontent"
file_path=$(jq -r '.tool_input.file_path // empty')
[ -z "$file_path" ] && exit 0

case "$(basename "$file_path" 2>/dev/null)" in
  judge.py|server.py|generators.py|providers.py) ;;
  *) exit 0 ;;
esac

cd "$REPO_DIR" || exit 0
python3 tools/bughunt/bughunt.py --quick >/tmp/bughunt-hook.log 2>&1
rc=$?

if [ "$rc" -ne 0 ]; then
  jq -n \
    --rawfile report "$REPO_DIR/tools/bughunt/report.md" \
    --arg file "$file_path" \
    '{
      systemMessage: ("bughunt: a quick check failed after editing " + $file),
      hookSpecificOutput: {
        hookEventName: "PostToolUse",
        additionalContext: $report
      }
    }'
fi

exit 0

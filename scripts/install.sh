#!/usr/bin/env bash
#
# Install Mag-loop into a target repository.
#
# Copies the three skills into .claude/skills/, creates the labels the loop
# needs, and checks the prerequisites that otherwise fail confusingly hours
# later. Safe to re-run: every step is idempotent.
#
#   ./install.sh                    # install into the current repository
#   ./install.sh --target ../myapp  # install somewhere else
#   ./install.sh --dry-run          # report what would change, touch nothing
#   ./install.sh --no-labels        # skip label creation
#
set -euo pipefail

MIN_CLAUDE_VERSION="2.1.71"
SKILLS=(mag-spec mag-build mag-review)

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -d "$PACKAGE_DIR/skills" ]] || PACKAGE_DIR="$(cd "$PACKAGE_DIR/.." && pwd)"

TARGET="$PWD"
DRY_RUN=0
DO_LABELS=1
problems=0
warnings=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
warn() { printf '  \033[33mwarn\033[0m  %s\n' "$*"; warnings=$((warnings + 1)); }
bad()  { printf '  \033[31mfail\033[0m  %s\n' "$*"; problems=$((problems + 1)); }
run()  { if [[ $DRY_RUN -eq 1 ]]; then printf '  would run: %s\n' "$*"; else "$@"; fi; }

usage() { sed -n '3,13p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)   TARGET="${2:?--target needs a directory}"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    --no-labels) DO_LABELS=0; shift ;;
    -h|--help)  usage ;;
    *) say "unknown option: $1"; say "try --help"; exit 2 ;;
  esac
done

version_at_least() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

say "Mag-loop installer"
say "  package: $PACKAGE_DIR"
say "  target:  $TARGET"
[[ $DRY_RUN -eq 1 ]] && say "  mode:    dry run, nothing will be changed"
say ""

# ---- prerequisites ---------------------------------------------------------

say "Checking prerequisites"

for skill in "${SKILLS[@]}"; do
  [[ -f "$PACKAGE_DIR/skills/$skill/SKILL.md" ]] \
    || bad "package is incomplete: skills/$skill/SKILL.md is missing"
done
[[ $problems -eq 0 ]] && ok "package contains all ${#SKILLS[@]} skills"

TARGET="$(cd "$TARGET" 2>/dev/null && pwd || true)"
if [[ -z "$TARGET" ]]; then
  bad "target directory does not exist"
elif ! git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
  bad "target is not a git repository: $TARGET"
else
  ok "target is a git repository"
fi

if command -v claude >/dev/null 2>&1; then
  claude_version="$(claude --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
  if [[ -n "$claude_version" ]] && version_at_least "$claude_version" "$MIN_CLAUDE_VERSION"; then
    ok "Claude Code $claude_version (needs $MIN_CLAUDE_VERSION for /loop)"
  else
    bad "Claude Code ${claude_version:-unknown} is older than $MIN_CLAUDE_VERSION; /loop is unavailable"
  fi
else
  warn "claude not on PATH; cannot verify the version that provides /loop"
fi

have_gh=0
if command -v gh >/dev/null 2>&1; then
  if gh auth status >/dev/null 2>&1; then
    have_gh=1
    ok "gh is authenticated"
  else
    bad "gh is installed but not authenticated; run: gh auth login"
  fi
else
  bad "gh is not installed; the skills call it for every issue, PR, and label"
fi

default_branch=""
if [[ $have_gh -eq 1 ]]; then
  if default_branch="$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null)"; then
    ok "repository reachable, default branch is $default_branch"
  else
    bad "gh cannot read this repository; check the origin remote and your access"
  fi
fi

if [[ $problems -gt 0 ]]; then
  say ""
  say "$problems prerequisite(s) failed. Nothing was installed."
  exit 1
fi

# ---- install the skills ----------------------------------------------------

say ""
say "Installing skills into $TARGET/.claude/skills"

for skill in "${SKILLS[@]}"; do
  src="$PACKAGE_DIR/skills/$skill/SKILL.md"
  dest="$TARGET/.claude/skills/$skill/SKILL.md"
  if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
    ok "$skill already up to date"
    continue
  fi
  [[ -f "$dest" ]] && say "  replacing an older copy of $skill"
  run mkdir -p "$(dirname "$dest")"
  run cp "$src" "$dest"
  ok "$skill installed"
done

# ---- labels ----------------------------------------------------------------

if [[ $DO_LABELS -eq 1 ]]; then
  say ""
  say "Creating labels"
  # name|colour|description
  while IFS='|' read -r name colour description; do
    [[ -z "$name" ]] && continue
    if run gh label create "$name" --color "$colour" --description "$description" --force \
        --repo "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" >/dev/null 2>&1; then
      ok "$name"
    else
      warn "could not create or update label $name"
    fi
  done <<'LABELS'
agent-ready|5319e7|Approved by a human; an agent may build this
blocked|e99695|Waiting on a specific human answer
agent-building|fbca04|Claimed by a build pass, released on every exit
loop-approved|0e8a16|No must-fix findings; evidence for a human merge decision
loop-changes-requested|d93f0b|Must-fix findings; back to the builder
needs-human-review|b60205|Escalated: scope conflict, missing CI, or a product call
loop-stuck|5a5a5a|Two repair rounds failed to converge
LABELS
fi

# ---- required checks -------------------------------------------------------

say ""
say "Checking merge evidence"
required_count=0
if [[ $have_gh -eq 1 && -n "$default_branch" ]]; then
  required_count="$(gh api "repos/{owner}/{repo}/branches/$default_branch/protection/required_status_checks" \
    --jq '.contexts | length' 2>/dev/null || echo 0)"
fi

if [[ "${required_count:-0}" -gt 0 ]]; then
  ok "$required_count required status check(s) on $default_branch"
else
  warn "no required status checks on ${default_branch:-the default branch}"
  say ""
  say "  mag-review refuses to apply loop-approved without a required check, so"
  say "  every pull request will escalate to needs-human-review until you add"
  say "  one in Settings -> Branches -> Branch protection rules. Mag-loop does"
  say "  not treat missing CI as green."
fi

# ---- done ------------------------------------------------------------------

say ""
if [[ $DRY_RUN -eq 1 ]]; then
  say "Dry run complete. Nothing was changed."
  exit 0
fi

say "Installed. $warnings warning(s)."
say ""
say "Next:"
say "  1. Run /reload-skills in Claude Code, or restart it."
say "  2. Confirm /skills lists mag-spec, mag-build and mag-review."
say "  3. Run /mag-spec and describe one small piece of work."
say "  4. Read the issue it files. If the contract is right, apply agent-ready."
say "  5. Run /loop /mag-build, and watch the first pass before walking away."

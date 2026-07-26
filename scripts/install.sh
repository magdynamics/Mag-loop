#!/usr/bin/env bash
#
# Install Mag-loop.
#
# The skills are repo-agnostic — they infer the repository from the working
# directory — so install them once for your whole machine, then enable each
# project separately. Labels are the only per-repository part.
#
#   ./install.sh --global          # install skills for EVERY project (~/.claude/skills)
#   ./install.sh --labels-only     # enable the current repo: labels + CI check
#   ./install.sh                   # install into this repo only, plus labels
#   ./install.sh --target ../myapp # ...or into another repo
#
# Add --dry-run to any of these to report without changing anything.
# Safe to re-run: every step is idempotent, and re-running is how you upgrade.
#
set -euo pipefail

MIN_CLAUDE_VERSION="2.1.71"
SKILLS=(mag-spec mag-build mag-review)

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[[ -d "$PACKAGE_DIR/skills" ]] || PACKAGE_DIR="$(cd "$PACKAGE_DIR/.." && pwd)"

MODE="repo"          # repo | global | labels
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

# Print the header comment block, stopping at the first line that is not a
# comment. Derived rather than a hardcoded line range, so editing the header
# above cannot silently truncate --help or leak code into it.
usage() {
  awk 'NR > 2 { if (!/^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --global|--user) MODE="global"; DO_LABELS=0; shift ;;
    --labels-only)   MODE="labels"; shift ;;
    --target)        TARGET="${2:?--target needs a directory}"; shift 2 ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --no-labels)     DO_LABELS=0; shift ;;
    -h|--help)       usage ;;
    *) say "unknown option: $1"; say "try --help"; exit 2 ;;
  esac
done

version_at_least() { [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]]; }

case "$MODE" in
  global) SKILL_ROOT="$HOME/.claude/skills"; SCOPE="every project on this machine" ;;
  repo)   SKILL_ROOT="$TARGET/.claude/skills"; SCOPE="this repository only" ;;
  labels) SKILL_ROOT=""; SCOPE="labels for this repository" ;;
esac

say "Mag-loop installer"
say "  package: $PACKAGE_DIR"
say "  scope:   $SCOPE"
[[ -n "$SKILL_ROOT" ]] && say "  skills:  $SKILL_ROOT"
[[ $DRY_RUN -eq 1 ]] && say "  mode:    dry run, nothing will be changed"
say ""

# ---- prerequisites ---------------------------------------------------------

say "Checking prerequisites"

for skill in "${SKILLS[@]}"; do
  [[ -f "$PACKAGE_DIR/skills/$skill/SKILL.md" ]] \
    || bad "package is incomplete: skills/$skill/SKILL.md is missing"
done
[[ $problems -eq 0 ]] && ok "package contains all ${#SKILLS[@]} skills"

# Only the per-repository modes care where they are run from.
if [[ "$MODE" != "global" ]]; then
  TARGET="$(cd "$TARGET" 2>/dev/null && pwd || true)"
  if [[ -z "$TARGET" ]]; then
    bad "target directory does not exist"
  elif ! git -C "$TARGET" rev-parse --git-dir >/dev/null 2>&1; then
    bad "target is not a git repository: $TARGET"
  else
    ok "target is a git repository"
  fi
  [[ "$MODE" == "repo" ]] && SKILL_ROOT="$TARGET/.claude/skills"
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

# gh is needed now only for label work; the skills need it at run time either way.
gh_required=0
[[ "$MODE" == "labels" || $DO_LABELS -eq 1 ]] && gh_required=1

have_gh=0
if command -v gh >/dev/null 2>&1; then
  # `gh api user` rather than `gh auth status`: the latter reports failure when a
  # perfectly usable token reports no OAuth scopes, which is how tokens injected
  # via GH_TOKEN in CI and containers behave. Test the call we actually depend on.
  if gh api user >/dev/null 2>&1; then
    have_gh=1
    ok "gh is authenticated"
  elif [[ $gh_required -eq 1 ]]; then
    bad "gh cannot reach the GitHub API; run: gh auth login (or check GH_TOKEN)"
  else
    warn "gh cannot reach the GitHub API; the skills need it at run time"
  fi
elif [[ $gh_required -eq 1 ]]; then
  bad "gh is not installed; it is needed to create labels"
else
  warn "gh is not installed; the skills call it for every issue, PR, and label"
fi

default_branch=""
if [[ $have_gh -eq 1 && "$MODE" != "global" ]]; then
  if default_branch="$(git -C "$TARGET" rev-parse --show-toplevel >/dev/null 2>&1 &&
      cd "$TARGET" && gh repo view --json defaultBranchRef --jq .defaultBranchRef.name 2>/dev/null)"; then
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

if [[ "$MODE" != "labels" ]]; then
  say ""
  say "Installing skills into $SKILL_ROOT"
  for skill in "${SKILLS[@]}"; do
    src="$PACKAGE_DIR/skills/$skill/SKILL.md"
    dest="$SKILL_ROOT/$skill/SKILL.md"
    if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
      ok "$skill already up to date"
      continue
    fi
    [[ -f "$dest" ]] && say "  replacing an older copy of $skill"
    run mkdir -p "$(dirname "$dest")"
    run cp "$src" "$dest"
    ok "$skill installed"
  done

  if [[ "$MODE" == "global" ]]; then
    repo_copies="$(find "$PWD/.claude/skills" -maxdepth 2 -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')"
    if [[ "$repo_copies" != "0" ]]; then
      warn "this repository also has $repo_copies skill file(s) in .claude/skills"
      say "  A repository copy shadows the global one. Delete it once the global"
      say "  install works, or it will keep serving an older version here."
    fi
  fi
fi

# ---- labels ----------------------------------------------------------------

if [[ $DO_LABELS -eq 1 ]]; then
  say ""
  say "Creating labels"
  name_with_owner="$(cd "$TARGET" && gh repo view --json nameWithOwner --jq .nameWithOwner)"
  while IFS='|' read -r name colour description; do
    [[ -z "$name" ]] && continue
    if run gh label create "$name" --color "$colour" --description "$description" --force \
        --repo "$name_with_owner" >/dev/null 2>&1; then
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

if [[ "$MODE" != "global" ]]; then
  say ""
  say "Checking merge evidence"
  required_count=0
  if [[ $have_gh -eq 1 && -n "$default_branch" ]]; then
    required_count="$(cd "$TARGET" && gh api \
      "repos/{owner}/{repo}/branches/$default_branch/protection/required_status_checks" \
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
fi

# ---- done ------------------------------------------------------------------

say ""
if [[ $DRY_RUN -eq 1 ]]; then
  say "Dry run complete. Nothing was changed."
  exit 0
fi

say "Done. $warnings warning(s)."
say ""
case "$MODE" in
  global)
    say "Next:"
    say "  1. Run /reload-skills in Claude Code, or restart it."
    say "  2. Confirm /skills lists mag-spec, mag-build and mag-review — in any project."
    say "  3. Enable each project you want the loop in:"
    say "       cd /path/to/project && $PACKAGE_DIR/install.sh --labels-only"
    ;;
  labels)
    say "This repository is now enabled. Next:"
    say "  1. Run /mag-spec here and describe one small piece of work."
    say "  2. Read the issue it files. If the contract is right, apply agent-ready."
    say "  3. Run /loop /mag-build, and watch the first pass before walking away."
    ;;
  repo)
    say "Next:"
    say "  1. Run /reload-skills in Claude Code, or restart it."
    say "  2. Confirm /skills lists mag-spec, mag-build and mag-review."
    say "  3. Run /mag-spec and describe one small piece of work."
    say "  4. Read the issue it files. If the contract is right, apply agent-ready."
    say "  5. Run /loop /mag-build, and watch the first pass before walking away."
    say ""
    say "To use Mag-loop across many projects, install it once with --global"
    say "instead, then run --labels-only in each project."
    ;;
esac

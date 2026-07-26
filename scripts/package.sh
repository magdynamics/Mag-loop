#!/usr/bin/env bash
#
# Build the shareable Mag-loop package.
#
# Produces dist/mag-loop-<version>.tar.gz containing everything a developer
# needs and nothing they do not: the three skills, the installer, and the team
# guide. The repository's own tooling — validator, CI, verify-loop — stays out.
#
set -euo pipefail

VERSION="${1:-0.1.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="mag-loop-$VERSION"
STAGE="$ROOT/dist/$NAME"

command -v node >/dev/null 2>&1 || { echo "node is required to validate before packaging" >&2; exit 1; }

echo "Validating before packaging"
node "$ROOT/scripts/validate.mjs"

rm -rf "$ROOT/dist"
mkdir -p "$STAGE/skills"

for skill in mag-spec mag-build mag-review; do
  mkdir -p "$STAGE/skills/$skill"
  cp "$ROOT/skills/$skill/SKILL.md" "$STAGE/skills/$skill/SKILL.md"
done

cp "$ROOT/scripts/install.sh" "$STAGE/install.sh"
chmod +x "$STAGE/install.sh"
cp "$ROOT/docs/TEAM-GUIDE.md" "$STAGE/TEAM-GUIDE.md"
printf '%s\n' "$VERSION" > "$STAGE/VERSION"

cat > "$STAGE/README.md" <<'PACKAGE_README'
# Mag-loop

Three Claude Code skills that turn GitHub Issues and pull requests into a
human-gated software factory. An agent writes the code; a person decides what
gets built and what gets merged.

**idea → `/mag-spec` files the issue → you label it `agent-ready` →
`/mag-build` opens a PR → `/mag-review` posts a verdict → you merge.**

One rule: **humans merge.**

## Install

Mag-loop is a machine-wide skill set. The skills name no repository — they infer
it from your working directory — so install them once, then enable each project.

```bash
./install.sh --global                    # once per machine -> ~/.claude/skills/

cd ~/code/some-project
/path/to/this/install.sh --labels-only   # once per project: labels + CI check
```

Then run `/reload-skills` in Claude Code and confirm `/skills` lists
`mag-spec`, `mag-build`, and `mag-review` — in any repository.

Add `--dry-run` to either command to report without changing anything. Both are
idempotent, and re-running `--global` upgrades every project at once.

Requires a GitHub repo with a working `origin`, Claude Code 2.1.71+, and `gh`
authenticated with write access. You also want at least one **required** status
check on your default branch — without one, `mag-review` escalates every pull
request instead of approving it, by design.

## Then read

`TEAM-GUIDE.md`. It is short, and it is the whole contract: how to write a spec
the builder can execute, how to read a verdict, what the seven labels mean and
who owns each, and when to use an ordinary Claude Code session instead.

## Contents

    install.sh              --global once, --labels-only per project
    TEAM-GUIDE.md           read this before your first run
    skills/mag-spec/        interviews you, files the issue
    skills/mag-build/       claims one issue, opens one PR
    skills/mag-review/      reviews one PR, posts one verdict
    VERSION

## Credit

A port of Finn-loop (https://github.com/finna/Finn-loop) by Alex Finn, MIT,
adapted to run on GitHub Issues instead of Linear.
PACKAGE_README

tar -czf "$ROOT/dist/$NAME.tar.gz" -C "$ROOT/dist" "$NAME"
(cd "$ROOT/dist" && zip -qr "$NAME.zip" "$NAME" 2>/dev/null) || echo "  (zip unavailable, tarball only)"
rm -rf "$STAGE"

echo ""
echo "Built:"
for f in "$ROOT/dist/$NAME".*; do
  [[ -f "$f" ]] && printf '  %s  (%s)\n' "${f#"$ROOT/"}" "$(du -h "$f" | cut -f1)"
done

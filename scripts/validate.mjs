// Guards the safety properties of the three skills. These are prompts, so they
// have no type checker and no runtime — this script is the only thing standing
// between an edit and a builder that merges its own work.

import { existsSync, readFileSync, readdirSync } from "node:fs";

const root = new URL("../", import.meta.url);
const failures = [];

const read = (relativePath) => readFileSync(new URL(relativePath, root), "utf8");

function check(condition, message) {
  if (!condition) failures.push(message);
}

const expected = ["mag-build", "mag-review", "mag-spec"];
const found = readdirSync(new URL("skills/", root), { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort();

check(
  JSON.stringify(found) === JSON.stringify(expected),
  `skills/ must contain exactly ${expected.join(", ")}; found ${found.join(", ") || "nothing"}`,
);

const skills = {};

for (const name of expected) {
  const path = `skills/${name}/SKILL.md`;
  if (!existsSync(new URL(path, root))) {
    check(false, `${path} is missing`);
    continue;
  }

  const text = read(path);
  skills[name] = text;

  const frontmatter = text.match(/^---\n([\s\S]*?)\n---\n/);
  if (!frontmatter) {
    check(false, `${path} is missing YAML frontmatter`);
    continue;
  }

  const fields = frontmatter[1].split("\n").filter((line) => line.trim());
  const declaredName = fields.find((l) => l.startsWith("name: "))?.slice(6).trim();
  const description = fields.find((l) => l.startsWith("description: "))?.slice(13).trim();

  check(fields.length === 2, `${path} frontmatter must contain only name and description`);
  check(declaredName === name, `${path} declares name "${declaredName}", expected "${name}"`);
  check(Boolean(description), `${path} needs a description so the skill triggers reliably`);
  check(
    !description || description.length <= 500,
    `${path} description is ${description?.length} chars; keep it under 500`,
  );
}

// Contract needles are matched against whitespace-normalised text so that
// re-wrapping a paragraph never fails the build for a phrase that is still there.
const flat = Object.fromEntries(
  Object.entries(skills).map(([name, text]) => [name, text.replace(/\s+/g, " ")]),
);
const { "mag-spec": spec, "mag-build": build, "mag-review": review } = flat;

// Each entry is a property that, if it silently disappeared, would let the loop
// merge unreviewed code, expand its own scope, or spin without converging.
const contracts = [
  [spec, "Never apply the `agent-ready` label", "spec must not self-approve its own issues"],
  [spec, "AC-N", "spec must emit stable acceptance-criteria ids"],
  [spec, "NG-N", "spec must emit stable non-goal ids"],
  [spec, "no cap on rounds", "spec must not cap interview rounds"],

  [build, "git status --porcelain", "builder must refuse to run on a dirty worktree"],
  [build, "defaultBranchRef", "builder must detect the default branch"],
  [build, "no:assignee", "builder must only claim unassigned issues"],
  [build, "-label:blocked", "builder's pick query must exclude blocked issues itself, not in prose"],
  [build, "sort:created-asc", "builder must take the oldest ready issue first"],
  [build, "loop-stuck", "builder must cap repair rounds and escalate"],
  [build, "If two rounds have already happened", "builder must stop after two failed repair rounds"],
  [build, "needs-human-review", "builder must honour the human escalation label"],
  [build, "Closes #N", "builder must link the PR to its issue"],
  [build, "Other behavior changes: None", "builder must ship a scope ledger"],
  [build, "never enable auto-merge", "builder must not merge"],

  [review, "--required", "reviewer must inspect required checks specifically"],
  [review, "re-fetch it", "reviewer must re-check the head sha before posting"],
  [review, "gh pr edit NUMBER --add-label", "reviewer must be given the label commands, not just a table"],
  [review, "isDraft,headRefName,", "reviewer must request the head branch in its PR listing"],
  [review, "starts with `mag/`", "reviewer must scope itself to builder branches by default"],
  [review, "Skip every other branch", "reviewer must say what to do with PRs outside its scope"],
  [review, "not treat absent CI as green", "reviewer must escalate when CI is unconfigured"],
  [review, "SCOPE-CONFLICT", "reviewer must escalate acceptance/non-goal conflicts"],
  [review, "Never push commits", "reviewer must not push to the branch it reviews"],
  [review, "Never merge, and never enable auto-merge", "reviewer must not merge"],
];

for (const [text, needle, message] of contracts) {
  check(text?.includes(needle), `${message} (missing: "${needle}")`);
}

check(!build?.includes("origin/main"), "builder hardcodes origin/main instead of detecting the default branch");
check(!spec?.includes("agent-ready` label yourself"), "spec must never apply the approval label");

// The two skills talk to each other through PR comment markers: the reviewer
// writes them, the builder greps for them. Renaming one file and not the other
// breaks nothing loudly — the repair queue just silently stops draining.
const REVIEW_MARKER = "Mag-loop review of <sha>";
const FIX_MARKER = "Mag-loop fix round N";

check(review?.includes(REVIEW_MARKER), `reviewer must stamp its verdict "${REVIEW_MARKER}"`);
check(build?.includes(REVIEW_MARKER), `builder must read the same verdict marker "${REVIEW_MARKER}"`);
check(build?.includes(FIX_MARKER), `builder must stamp and count repair rounds as "${FIX_MARKER}"`);

// Same coupling, one skill further back: the builder honours blocked-by chains
// by parsing a section only the spec skill ever writes.
const BLOCKED_BY = "Blocked by #N";
check(spec?.includes("## Blocked by"), "spec must emit the Blocked by section the builder parses");
check(spec?.includes(BLOCKED_BY), `spec must document the "${BLOCKED_BY}" form it writes`);
check(build?.includes(BLOCKED_BY), `builder must parse the same "${BLOCKED_BY}" form`);

// agent-building is a claim on an issue. Every path that stops working an issue
// has to drop it, or the issue is stranded: the pick query only returns
// unassigned issues, so a stale claim is permanent.
const RELEASE = "--remove-label agent-building --remove-assignee @me";
check(
  build?.includes(`gh issue edit N --add-label blocked ${RELEASE}`),
  "builder must release agent-building when blocking an issue",
);
check(
  build?.includes("appears in no open pull request body as `Closes #N`"),
  "builder must reclaim issues stranded by a crashed pass or a closed pull request",
);
check(
  build?.includes("assigned to you or to nobody"),
  "builder's reclaim sweep must not strip work a human has taken",
);
check(
  (build?.match(new RegExp(RELEASE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "g")) ?? []).length >= 3,
  "builder must release its claim on all three exit paths: reclaim, abandoned claim, and blocked",
);

for (const [name, text] of Object.entries(skills)) {
  check(!/\bLinear\b/.test(text), `skills/${name}/SKILL.md still references Linear; this port uses GitHub Issues`);
  check(!/\bTEAM\b/.test(text), `skills/${name}/SKILL.md left a TEAM placeholder from the Linear original`);
}

const readme = read("README.md");
for (const [, target] of readme.matchAll(/\[[^\]]+\]\(([^)]+)\)/g)) {
  if (!target.startsWith("http") && !target.startsWith("#")) {
    check(existsSync(new URL(target, root)), `README links to a path that does not exist: ${target}`);
  }
}
check(readme.includes("/reload-skills"), "README must tell the user to reload skills after installing");
check(readme.includes("humans merge"), "README must state the governing rule");

// The product is "Mag-loop" and the repository is magdynamics/Mag-loop. Both
// have already been spelled other ways; an install prompt pointing at the old
// repository name sends users somewhere that only works by GitHub redirect.
for (const [name, text] of [["README.md", readme], ...Object.entries(skills)]) {
  check(!text.includes("Mag Loop"), `${name} spells the product "Mag Loop"; it is "Mag-loop"`);
  check(!text.includes("Mag-Loop-"), `${name} references the old repository name Mag-Loop-`);
}

if (failures.length) {
  console.error(`Mag-loop validation failed (${failures.length}):\n`);
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}

console.log(`Validated ${expected.length} skills, ${contracts.length} safety contracts, and README links.`);

---
name: mr-review
description: 'Review a GitLab merge request with merge-train, and re-check it after the author updated the branch ("review update"). Prepares the local clone at the MR head, builds and tests, traces the changes against the requirements (MR description, linked issue, or what a project skill supplies), and writes the findings as a review JSON that merge-train shows as agent hints at their lines in the MR diff. The user turns them into GitLab comments there; the reviewed code stays untouched. Use when the user asks to review a MR or branch ("review !42", "review this MR", "schau dir den MR an", "review update"). If a project skill builds on this one (e.g. jira-review for ticket keys), follow that one: it adds requirements and project specifics and points back here.'
argument-hint: "[MR-URL | gruppe/projekt!42 | branch]"
---

# MR review with merge-train

You prepare a code review; the user decides. Never fix the reviewed code, never commit, never push, never comment in
GitLab or a ticket system. Everything you find goes into the chat (overview) and into the review JSON (details and
copy-ready comments), which merge-train shows in the MR diff. Publishing to GitLab is the user's step in merge-train.

merge-train is on the PATH (`merge-train agent <befehl> --help`). Format of the review JSON and every output of
`pruefen`/`zeigen`: `docs/agent-hinweise.md` in the merge-train repo (this skill lives in `skill/mr-review` there,
so `../../docs/agent-hinweise.md` from this file). Read it once per session before writing the JSON. How to name
yourself (`--als`, field `agent`): "Say who you are" in the `merge-train` skill.

**Extending.** A project skill on top of this one supplies what is specific: where the requirements come from
(step 1), build and test commands (step 3), repo specifics (submodules, branch naming), languages and the file key
(step 6). Where it says something, it wins; everything else comes from here.

## 1. Requirements and context

1. The MR: from the arguments (URL, `gruppe/projekt!42`), else the open MR of the branch – `"branch"` in the JSON is
   enough, `pruefen` finds it. Read its description (read only, e.g. `glab mr view <iid>`).
2. Requirements: what the change is supposed to do. Without a project skill: the MR description and a linked issue.
   Note acceptance criteria and **decisions made in comments** (who decided what, when) – they often change the scope.
3. Read the repo conventions (`AGENTS.md`, `CONTRIBUTING.md`, `README.md`) before judging the code. Look for existing
   follow-ups/TODOs (e.g. `tasks/`) before reporting something as new.
4. Existing comments at the MR: `merge-train agent kommentare <MR>` (drafts, staged/sent comments and GitLab
   discussions as of the last fetch) – don't report what is already commented.

## 2. Branch

merge-train reads diff, files and commits only from the local clone: the MR's source branch (local branch, else
`origin/…`) against the merge base with the target branch. So the local branch must be at the MR head.

1. `git fetch origin --prune`, find the source branch. Several candidates → ask which one.
2. The working tree must be clean (`git status --porcelain --untracked-files=no`), otherwise ask. Switch **in place**
   (no worktree), then `git merge --ff-only origin/<branch>`. Keep it clean for the whole review: never edit reviewed
   files, not even for markers.
3. Submodules: if the branch needs a submodule branch of its own, **suggest** the checkout; don't change submodules
   yourself. A submodule commit that is not committed as pointer in the parent is a finding, not a blocker.

## 3. Build and tests

- Build what the branch touches, with the repo's own commands (conventions file, README, CI config). If the build
  fails, find the cause first (often a missing submodule branch); **never** run tests against stale binaries.
- After a fresh build: unit tests of the affected projects/packages. Integration tests only when the user asks.
  Report numbers honestly, including what was not run.

## 4. Analysis

Diff against the merge base: `git diff $(git merge-base HEAD origin/<target>) HEAD`, plus
`git log --format='%h %ad %an %s' --date=short` for the timeline.

- **Requirements check:** every acceptance criterion → where it is implemented, or the deviation. Wording (UI labels,
  titles, formats) counts.
- **Decisions vs. code:** decisions in comments that change the scope – are they reflected in the code (and in
  related issues)? Note contradictions.
- **Order of work:** does the branch build something a dependency should have delivered (tables nobody fills, data
  only created by test inserts)?
- **Precedent:** compare new mechanisms (transactions, scheduling, contracts, enums, filters, i18n) with existing
  patterns in the codebase; a new mechanism without precedent and without rationale is a finding.
- **Dead code** (`git log -S` to find when it became unused), duplication (copied files or code that largely repeats
  another file: give each pair a `see_also` with `"diff"`, a range comparison when only parts repeat), unbounded queries/in-memory loads, time-zone handling, formatting-only noise in unrelated
  files.
- **Tests:** for each changed production file, is there a test? Note missing tests for real behavior (not for DTOs or
  configuration).
- Suspected bugs: write a small repro test in a scratch folder, copy it into the project temporarily, run it, remove
  it again. Keep the scratch copy and note how to run it.

## 5. Findings and decisions

- Number them: `#1…` for real issues, `K1…` for minor ones. For each: problem, evidence (file:line, commit,
  issue/comment), proposal.
- Present them in the user's language and ask for a decision where it is not obvious. Put the decision into the
  comment text and into `decision`. Topics outside the MR's scope go where the repo keeps follow-ups (e.g.
  `tasks/TODO-<topic>.md`: background, findings, open questions – no solution unless decided).
- Overview in the chat as a table `# | Problem | Entscheidung | Status` (the problem column is mandatory). Show it again
  when statuses change ("done by author" ≠ pushed: re-check origin).

## 6. Review JSON

The review JSON is the only record of the findings. Default place: `tasks/<KEY>-review-markers.json` in the repo,
`KEY` = ticket key if there is one, else `MR<iid>`. A repo without its own `tasks/` (e.g. a submodule repo): put the
JSON into `tasks/` of the repo the work is tracked in, with `"mr"` set, and run `pruefen`/`zeigen` from the clone of
the MR's repo (see "Zuordnung zum Merge-Request" in the docs). Field reference: `docs/agent-hinweise.md`, "Format".

What makes the entries good:

- **One entry per finding location**; several entries may share a finding. Every in-scope finding gets an entry –
  none may live only in the chat. Mark the first relevant line; JSON, i18n, assets, SQL and docs can be pointed at
  directly. A finding without a sensible line (structure, MR scope): entry without `path`/`needle` → general comment.
- `text` is the final GitLab comment, in the team's review language (English unless the repo or a project skill says
  otherwise). Write it like a colleague's review comment: plain and short (usually 2–4 sentences) – what is the
  problem, why it matters (a concrete failure example where it helps), what to do instead.
  - **No finding IDs** in `text`: the author walks through GitLab file by file, local numbering looks random there.
    IDs stay in `finding`.
  - Refer to other places **by file or class name, without line numbers**; the exact location goes into `see_also`.
  - Name the proposal, don't spell it out (no full signatures). Verify the named API/pattern exists, or mark it as new.
    If the framework has a ready-made API for the fix, name that exact API instead of describing the behavior, and
    check it exists in the project's target version.
  - At most a few technical terms; no lists of every affected method. "Check whether…" is not a proposal.
  - No vague shorthand: every term must be clear to the author without asking back. Parenthetical reasons must stand
    on their own: what happens, where, why it matters.
  - Non-obvious mechanisms (locks, transactions, concurrency, caching, ordering, cross-module dependencies) need the
    chain explained: who else uses it, what happens when, the consequence. Up to about twice the usual length, with a
    `see_also` for every dependency the author has to look at.
  - Removal proposals end with "…, or explain why it should stay."
  - Missing tests: "Missing test: <what should be tested>" at a related test or the changed code.
  - Follow-up entries of the same finding stay short: "Same as in <file/class>: …".
- **"Now unused / replaced" findings:** anchor the entry at the cause in the diff (the new code that replaced the old),
  not at the orphan. `see_also` points to the orphan and to the caller line where the old call was swapped. If the new
  code repeats the old, add a `see_also` with `"diff"` to the old counterpart (preferably as a range comparison).
- `needle`: text on the line in the MR state (substring; with `=` the whole line). `line` only if no needle can be
  made unique.
- `see_also`: **every place the `text` mentions** (another file, class, i18n key, "already exists in …") gets one – a
  comparison without the link is useless. Always with a line or range, the most telling one; file-only only with
  `"diff"` or when the whole file is meant. Never link the marker's own block. Copies: `"diff": true` (or
  `"diff": "other/path"`, ranges as in the docs).
- `title`: a few keywords in the user's language for merge-train's comment list; follow-up entries say so ("… (zu #4)").
- `problem`/`decision`/`status`: from the chat overview (user's language). `agent` on top level, always.

After every write of the JSON, from the repo root:

```sh
merge-train agent pruefen tasks/<KEY>-review-markers.json   # read only: where each entry lands in the MR
merge-train agent zeigen  tasks/<KEY>-review-markers.json   # register the file with the MR and open it in the browser
```

- The merge-train server need not be running: `pruefen` works without it, `zeigen` starts it if needed.
- Without a recognized harness add `--als "<Harness> (<Model>)"`, the same string as in `agent`.
- `pruefen` until the output is clean (`FEHLT` = fix `needle`/`path`/`see_also`; `needle passt N×` = make it unique),
  then `zeigen` once when the user wants to look at it. Meaning of every output line and exit code: docs.
- `Achtung: GitLab steht auf …` or exit 3: the local branch is not at the MR head → step 2, then again.
- Resolved or dropped findings: remove them from the JSON. A changed `text` shows up as a new hint; comments the user
  already took over stay in merge-train.

## Review update

When the user says the branch was updated ("review update", "schau nochmal drüber, was behoben ist"):

1. `git fetch`, fast-forward (step 2). Build and run the affected tests again (step 3).
2. `merge-train agent pruefen <json> --seit` (against `reviewed_commit`; `--seit <sha>` for another base):
   - `WEG` / `GEÄNDERT`: the entry's file or line is gone → read `git diff <reviewed_commit> HEAD -- <path>` and judge
     it against `resolved_when`.
   - `offen*`: line still there but the file changed → the fix may sit elsewhere in it.
   - `offen`: untouched. Fixes that are additions (comment, test, i18n key) stay `offen` → check `resolved_when` by hand.
   - Also scan `git log <reviewed_commit>..HEAD` for commits that touch none of the entries' files but may address a
     finding, and for new problems introduced by the fixes.
3. Report as a table `Finding | Status (behoben / teilweise / offen / neu) | Begründung` – only what changed.
4. Update the JSON: drop resolved entries, adjust partially resolved ones, add new findings, set
   `reviewed_commit`/`reviewed_at`, keep `agent`. Then `pruefen` again – the open page refreshes itself.

## Language

Chat, `title`, `problem`, `decision` and follow-up files in the user's language; `text` (the GitLab comment) in the
team's review language. Content from issues or tickets: translate when reporting, keep keys and identifiers verbatim.

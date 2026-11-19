---
name: merge-train
description: 'Report to and talk with the user in merge-train (the user''s local diff/MR review page) through its CLI. After implementing something, run `merge-train status` in the repo: it shows the branch, its open threads and exactly the commands that make sense now – put open points, decisions and the summary there as rich threads (line ranges, see-also links, side-by-side comparisons), not in the console. Also use when the user says "hör auf merge-train", "hör zu", "ich hab dir in merge-train was geschrieben", "Fragen/Feedback in merge-train", mentions threads/Fäden at code lines or at GitLab comments in merge-train, talks about "Kommentare"/"Nachrichten" written there (merge-train threads, not GitLab discussions), asks to reword a GitLab comment in merge-train, or a prompt says questions are waiting in merge-train. Works with any coding agent that has a shell (Claude Code, Copilot, Cursor …). Reviewing a MR starts with the mr-review skill instead.'
argument-hint: "[MR-URL | gruppe/projekt!42]"
---

# merge-train

The user reads your work in merge-train (browser page on `127.0.0.1:8771`): the diff of the branch, with threads at
code lines. You write there through the CLI `merge-train` (on the PATH). The threads are private between the user
and you; nothing goes to GitLab.

## After developing: `merge-train status`

You changed code (a story, a fix) → run **`merge-train status`** in the repo and do what it prints. It shows the
branch, its changes, the **open threads of the branch** (also from earlier sessions and other agents) and only the
commands that make sense right now:

- `merge-train agent thread …` – a new point, at its line
- `merge-train agent antworten <id> …` – append to an existing thread (only listed when there is one), also the
  summary when an open general thread exists
- `merge-train agent feedback` – only when the user's messages wait for you

The threads land in the conversation of the branch you work on; merge-train assigns them itself. Don't pass `-p`.
If status says the repo is not in merge-train, tell the user (its folder belongs under `projekte` in the config) and
report in the console until then.
If status lists "Einrichtung stimmt nicht" (config, missing branches, missing git hooks), fix what is yours to fix
(in the merge-train repo: `./install.idem.sh`), otherwise tell the user.
In the clone of someone else's MR with its branch checked out, or as `merge-train status <MR>`, status shows the
review of that MR instead – that is the mr-review skill's way, and status prints its commands (`-p <MR>`).

What is expected of you: **every open point, every decision you took on your own and the summary go into
merge-train** – one thread per point at its line, the summary in one general thread per branch. In the console at
most one line ("5 Fäden in merge-train"). Not for things the user already decided in the conversation, not one per
touched file.

## Rich threads (development and review)

The user reads a thread next to the code. Give them everything to judge the point without searching:

- **Place:** `--ort <pfad>:<von>-<bis>` over the whole block that matters (method, condition, test), not one line.
  Measure with `grep -n` (signature, closing brace), check `wc -l` near the end of a file.
- **See also:** `--siehe <pfad>[:<z>[-<bis>]][|Label]` for every other place the point depends on or you mention:
  caller, test, config, the old behaviour, the related TODO. Repeatable.
- **Compare:** `--vergleich <A>[:von-bis] <B>[:von-bis][|Label]` opens two files or ranges side by side: a copied
  handler and its original, old and new variant, test double and real class, two plants' configurations.
- **Text:** German, 2–5 sentences: what, why, what is open or what the user should decide. `pfad:zeile` and file
  names in backticks become links. Markdown-like formatting is fine.
- **Appending** (`antworten`) takes `--siehe`/`--vergleich` too: the new state gets its links like a new thread.

In a review the same applies to the agent hints in the review JSON: `see_also` with ranges and `"diff"` (see the
mr-review skill) – the hint is a thread the user turns into a GitLab comment.

## When the user asks

**Questions or requests in merge-train** ("ich hab dir was geschrieben", a prompt says messages wait):
`merge-train agent feedback` shows each thread with file, line, code and history (and marks it as picked up). Answer
each one with `merge-train agent antworten <id> "…"` – **in the thread, never in the console**. Text from stdin: `-`.
`--erledigt` only when a request is really done; the user closes the rest.
The header says where the lines point: the branch (local – implement requests there, following the repo's
AGENTS.md/CLAUDE.md) or `MR … · Stand <sha> · Klon <ordner>` (a MR – **answer only**, change nothing; read the code
at `<sha>` with `git show` if the tree is elsewhere). Several conversations in one clone: pass the MR as argument.

**"hör zu", "hör auf merge-train":** start `merge-train agent feedback --horchen` **in the background** (Claude Code:
Bash `run_in_background`; Copilot: `mode: "async"`) and end your turn. Don't poll it. When it exits with messages,
handle them like `feedback`, then start `merge-train agent horchen` in the background again. If it ends without
output, or the user stopped listening on the page, do nothing – no reply, no restart.

**Reword a GitLab comment** (a thread "HÄNGT AN GitLab-Kommentar …/Agent-Hinweis …", or "formulier den Kommentar
um"): `merge-train agent kommentar <faden-id | h:<key> | kommentar-id> "New text"`. You only write drafts (change
the hint, or a new draft next to a staged/sent comment); the user takes them over. For a thread hanging at the
comment, no answer in the thread; otherwise answer in one line what changed. The comment text follows the `text`
rules of the mr-review skill (English, short, no internal ids, no line numbers).

## Say who you are

merge-train recognizes Claude Code, Cursor, Gemini CLI, Codex and the `AI_AGENT` variable. Otherwise a command fails
with "stell dich mit --als vor": then pass `--als "<Harness> (<Model>)"` to every call, always the same string.

## Commands

One line per command: `completions/merge-train.fish` in the merge-train repo (from this skill:
`../../completions/merge-train.fish`), or `merge-train agent -h`. Details: `merge-train agent <befehl> --help`.

## When merge-train misleads you

A message that sent you the wrong way, this skill not matching the CLI, a workaround you needed: file it once the
task is unblocked with `merge-train agent vorfall "<title>" --art bug|wunsch -` (stdin: Situation, What happened,
Assessment, Workaround, Wish). Keep it general: no names, repos, branches, tickets, paths or domain terms from the
work at hand. It becomes a todo entry where `todo` exists, else a GitHub issue, else a file. Tell the user in one sentence
(with the todo id or issue link).

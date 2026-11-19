---
name: merge-train
description: 'Answer the user''s questions and feedback from merge-train (the user''s local diff/MR review page) — fetch them with `merge-train agent feedback`, answer each thread with `merge-train agent antworten`, reword GitLab comments with `merge-train agent kommentar`, listen for more with `merge-train agent feedback --horchen` / `horchen` in the background, and open own threads (`merge-train agent thread`) for open points and the summary after implementing something. Use when the user says "hör auf merge-train", "hör zu", "ich hab dir in merge-train was geschrieben", "Fragen/Feedback in merge-train", mentions threads/Fäden at code lines or at GitLab comments in merge-train, or talks about "Kommentare"/"Nachrichten" it wrote there (these are merge-train threads, not GitLab discussions), or when a prompt says questions are waiting in merge-train. Works with any coding agent that has a shell (Claude Code, Copilot, Cursor …) and in any repo: the merge-train repo itself (local mode, changes allowed) and GitLab MR clones (answer only).'
argument-hint: "[MR-URL | gruppe/projekt!42]"
---

# merge-train

The user reviews code in merge-train (browser page on `127.0.0.1:8771`) and writes questions or requests at code
lines or at GitLab review comments. You pick them up via the CLI and answer per thread. Answers appear on the page
immediately (it polls every 4 s, plus a desktop notification). Nothing goes to GitLab: these threads are private
between the user and you.

`merge-train` is on the PATH (`~/.local/bin/merge-train`). You only need a shell. `merge-train agent <befehl> --help`
lists the options.

## Say who you are

The page shows the name of whoever answered, opened a thread, listens or wrote a hint. Never leave it at a generic
"Agent".

- merge-train recognizes some harnesses from the environment (Claude Code → "Claude", Cursor, Gemini CLI, Codex, the
  `AI_AGENT` variable). Then you need nothing.
- **Otherwise pass `--als "<Harness> (<Model>)"`** to every `antworten`, `thread`, `kommentar`, `horchen`, `pruefen`,
  `zeigen` (`feedback` needs none but tolerates it), e.g. `--als "Copilot (Claude Sonnet 4.5)"`, always the same string. Without a name, `thread`, `horchen` and
  `kommentar` fail with "stell dich mit --als vor". Then repeat the call with `--als`.
- In a review JSON (agent hints, see the mr-review skill and `docs/agent-hinweise.md` in the merge-train repo) put
  the same name in the top-level field `"agent"`.

## Two rules

1. **Answer in the thread, not in the console.** Every answer to a merge-train message goes through
   `merge-train agent antworten <id> …`. The user reads it at the code line on the page, not in your terminal.
   In the console, at most one line like "3 Fäden in merge-train beantwortet", never the answer itself.
2. **"Kommentare", "Nachrichten", "Fragen", "Feedback" – even "GitLab-Kommentare" – mean the merge-train
   threads** whenever they arrived via `horchen`/`feedback` or the user talks about what they wrote in merge-train.
   Don't fetch or post GitLab MR discussions (glab, API) yourself: the GitLab comments on a line reach you through
   merge-train (listed under each thread), and you change them only via `merge-train agent kommentar` (see below).

## Which conversation

Without an argument the commands use the current repo: its local conversation (if local mode is on) and all its
MRs the user has opened in merge-train. Pass an MR (URL, `host/gruppe/projekt/42`, `gruppe/projekt!42`) to narrow
it down, e.g. when several MRs share the clone or you are not inside the clone. The skill argument, if given, is
that MR.

## Fetch

```sh
merge-train agent feedback [MR]          # waiting threads; marks the messages as picked up
merge-train agent feedback [MR] --alle   # also answered threads (history)
```

The user may collect messages on the page and send them later. `feedback` picks up everything that was sent, also
without anyone listening.

The header says where the line numbers point:

- **Local mode** (`… · claude <sha>`): the current state of the `bis` branch (usually `claude`). Requests may be
  implemented there and committed, following the repo's AGENTS.md/CLAUDE.md.
- **MR** (`MR … · Stand <sha> · Klon <ordner>`): the MR's state `<sha>` in the local clone. **Answer only**: do
  not change, commit or push anything in the MR. If the checked-out tree is not at `<sha>`, read the code with
  `git show <sha>:<pfad>` / `git diff <basis>..<sha>` instead of the working tree.

Each thread shows the file, line, code around it and the history. Answer what is asked, against the actual code.

## Answer

```sh
merge-train agent antworten <id> "Text"             # id from feedback, a prefix suffices
merge-train agent antworten <id> --erledigt "Text"  # request implemented (local mode)
merge-train agent antworten <id> - <<'EOF'          # longer/multi-line text from stdin
…
EOF
#   --als "<Harness> (<Model>)"   if merge-train doesn't recognize you (see above)
```

- Write in the user's language (German), short and to the point, Markdown-like formatting is fine.
- Refer to code as `pfad:zeile`. Name the commit when you implemented something.
- One `antworten` call per thread. That is the answer; don't repeat it in the console. If a question is unclear, ask back in the thread instead of guessing.
- `--erledigt` only when a request is really done; for a plain answer leave the thread open (the user closes it).

## Writing or adjusting a GitLab comment

Often the user asks to reword a GitLab review comment, or a proposal ends in a new comment text.

A comment goes through three stages (merge-train's own terms, see `AGENTS.md` in the merge-train repo; the page
shows other labels, `feedback` uses these):

- **draft**: agent hint from the review JSON, not taken over yet. May still be changed, also by you.
- **staged**: taken over or written by the user (page: "Entwurf (lokal)"), goes out with "Review abschließen".
  **Only the user creates staged comments** (button "übernehmen"). You never do.
- **sent**: in GitLab as a draft note (GitLab's "draft" is *not* our draft).

The thread answer itself is German and internal; the **comment text** is for the MR author and follows the user's
GitLab comment conventions:

- Before writing it, read the rules for `text` in the mr-review skill (`skill/mr-review/SKILL.md` in the merge-train
  repo, step 6, "`text` is the final GitLab comment") and apply them, together with a project skill's additions
  (e.g. jira-review), plus the repo's notes on review comments if there
  are any (e.g. FE findings phrased as questions). They win over this summary.
- In short: English, plain and short (usually 2–4 sentences: problem, why it matters, what to do instead), in the tone
  of the user's commit messages.
- **No internal IDs**: no finding IDs (`#8`, `K2`), marker titles, thread or hint ids, nothing that only exists in
  merge-train or the review JSON. The author reads GitLab file by file and can't resolve them.
- Refer to other places **by class or file name**, without line numbers ("same copy as in the CVD handler"); exact
  locations belong in the review JSON's `see_also`, not in the comment.
- Name the proposal, don't spell it out (no full signatures); at most a few technical terms.

### Thread attached to a comment ("HÄNGT AN …")

The user can write at a comment itself ("💬 an Agent" on a comment or hint). In `feedback` such a thread shows
`HÄNGT AN GitLab-Kommentar <id> (…)` or `HÄNGT AN Agent-Hinweis h:<key> (…)` with the comment text. **The request is
about that text**, even when it is short ("kürzer", "ohne das zweite Beispiel", "freundlicher").

```sh
merge-train agent kommentar <faden-id> "New text"   # changes exactly that comment, then the thread is done
```

- This changes the draft directly, or adds a new draft next to a staged/sent comment. The thread then hangs at the
  draft and is marked done. **No answer in the thread**: the user sees the new text on the page.
- Answer with `antworten` only when the user asks for an explanation ("erklär mir …", "warum …?") or when the
  request is unclear. Then don't change the comment unless they asked for that too.

### Other threads at a comment's line

`feedback` also lists under each thread the GitLab comments and agent hints on the same line ("an dieser Zeile: …",
with id and full text). To change one of them:

```sh
merge-train agent kommentar h:<key> "New text"        # draft: changes the hint's text in the review JSON
merge-train agent kommentar <kommentar-id> "New text"  # staged or sent: new draft (agent hint) next to it
merge-train agent kommentar <faden-id> "New text"      # no comment there yet: new draft at the thread's line
merge-train agent kommentar <ziel> - <<'EOF'         # longer text from stdin
…
EOF
```

- You only ever write drafts: change an existing draft, otherwise add a new draft next to the staged/sent comment.
  The user takes it over ("übernehmen") or discards it and deletes the old comment if needed.
  Don't delete anything.
- Then answer the thread **very briefly**: "Done" for small things, otherwise one line on what changed (e.g. "Done:
  Finding-ID raus, auf 2 Sätze gekürzt"). Don't repeat the comment text in the thread.
- If it's unclear which comment is meant (several on the line, none listed), ask back in the thread.

## Starting threads yourself

You can open threads too, e.g. after implementing something: points the user should check, decisions you made
on your own, open questions. The user answers on the page; the answers reach you via `feedback`/`horchen` as usual.

Before adding your own remarks to a MR (threads or new review hints), read what is already commented there, so nothing
ends up twice. `feedback` only shows threads; a comment the user wrote without a thread does not appear there:

```sh
merge-train agent kommentare [MR]   # drafts, staged/sent comments and GitLab discussions with place, stage, id, text (read only)
```

```sh
merge-train agent thread --ort <pfad>:<zeile> "Text"      # at a code line (current state, see the header of feedback)
merge-train agent thread --ort <pfad>:<von>-<bis> "Text"  # at a range of lines (one --ort per thread; --siehe/--vergleich repeatable)
merge-train agent thread - <<'EOF'                         # general thread (no --ort), text from stdin
…
EOF
#   --siehe <pfad>[:<zeile>[-<bis>]][|Label]   "see also" link (repeatable)
#   --vergleich <A>[:von-bis] <B>[:von-bis][|Label]   two files (or just these line ranges) side by side in a popup (repeatable)
#   -p <MR|Projekt>                            other conversation (default: current repo, local before MR)
```

- **One thread per point**, at the line it is about: the problem or decision in 2–5 German sentences, what you
  chose and why, what is open or what the user should decide. Unsure about something → thread, don't bury it in
  a summary.
- `--siehe` for the other places that matter (caller, test, the old behaviour), `--vergleich` when two files should
  be read side by side (a copied handler, the old and the new variant, a test double and the real class).
- **General output** (summary of the work, test results, list of the points) goes into **one general thread**
  without `--ort`. File names and `pfad:zeile` in the text become links to the code on the page (exact path or
  a unique file name; best in backticks, like `Foo.cs:42`).
- Don't open threads for things the user already decided in the conversation, and don't open a thread per file
  you touched – only where there is something to read, decide or check.
- Measure `--ort` ranges, don't estimate them: start and end from `grep -n` (signature, `return`, closing brace),
  near the end of a file check `wc -l`. merge-train rejects lines past the end of the file.
- `thread` prints the id; leave it to the user to close the threads. If it fails with "kein Gespräch" or "Projekt …
  nicht gefunden", the repo is not in merge-train: tell the user that its folder belongs under `projekte` in the
  merge-train config (the message names the file; changes take effect without a restart), and report in the console
  until it is there.

## Listen

When the user asks you to listen ("hör auf merge-train", "hör zu"), or after answering when the prompt says so:

1. Start `merge-train agent feedback --horchen [MR]` **as a background process** of your harness, so you get its
   output when it exits (Claude Code: Bash with `run_in_background`; Copilot: bash with `mode: "async"`; elsewhere
   the harness's way to run a command in the background). It hands you what is already waiting at once, otherwise
   it waits like `horchen`. The page then shows „🎧 <your name> hört zu“, and „An Agent senden“ goes straight to you.
   Add `--als` if merge-train doesn't recognize you. Then end your turn: **don't poll** it (no `read_bash`/output
   reads in a loop) – your harness wakes you when it exits, every poll costs a request.
2. When it exits with messages, its output is the same as `feedback` (already marked as picked up): handle each
   thread as above (`antworten` or `kommentar`, not in the console), then start `merge-train agent horchen [MR]` in
   the background (only new messages).
3. When the user stops listening on the page (closes it, or „🎧 ✕“), the command does **not** exit and prints
   nothing: it waits silently until your session ends, so you are not woken. Leave it alone – don't read, stop or
   restart it. Should it ever end without output, do nothing at all (no reply, no restart). It ends with exit 1 and
   a message after `--timeout` or when your session ends; then don't restart either. "hör zu" starts it again.

Don't run it in the foreground (it blocks until the user sends) and don't start several at once for the same
conversation. If your harness can't run background commands, tell the user. The messages then wait on the page
until you fetch them with `feedback`.

## When merge-train misleads you: file an incident

If merge-train itself got in your way – a message that sent you the wrong way, a skill instruction (this one,
mr-review, a project skill) that did not match what the CLI does, a workaround you needed, or the user had to correct
you about how merge-train works – file a short report once the task is unblocked. It becomes an issue in
merge-train's GitHub repo (if that fails, a file in the inbox of the merge-train clone); whoever develops merge-train
works through it.

```sh
merge-train agent vorfall "<short title>" - <<'EOF'
## Situation
## What happened      (commands, exact messages, what you assumed)
## Assessment         (bug, missing feature, unclear docs – what you verified, what is only a guess)
## Workaround
## Wish               (what would have prevented it)
EOF
```

Keep it general: it describes merge-train, not the work at hand. No names of people, companies, projects, repos,
branches, tickets, file paths or domain terms from the repo you work in; use placeholders (`<submodule>/…`, "a MR
with submodules", "the target branch"). Write it in the user's language, facts only, and mark guesses as guesses.
One report per incident; tell the user in one sentence that you filed it (with the issue link). Not for problems in
the reviewed code or the user's repo.

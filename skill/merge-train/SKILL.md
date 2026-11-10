---
name: merge-train
description: Answer the user's questions and feedback from merge-train (the user's local diff/MR review page) — fetch them with `merge-train agent feedback`, answer each thread with `merge-train agent antworten`, and listen for more with `merge-train agent horchen` in the background. Use when the user says "hör auf merge-train", "hör zu", "ich hab dir in merge-train was geschrieben", "Fragen/Feedback in merge-train", mentions threads/Fäden at code lines in merge-train, or talks about "Kommentare"/"Nachrichten" it wrote there (these are merge-train threads, not GitLab discussions), or when a prompt says questions are waiting in merge-train. Works in any repo: the merge-train repo itself (local mode, changes allowed) and GitLab MR clones (answer only).
argument-hint: "[MR-URL | gruppe/projekt!42]"
---

# merge-train

The user reviews code in merge-train (browser page on `127.0.0.1:8771`) and writes questions or requests at code
lines. You pick them up via the CLI and answer per thread. Answers appear on the page immediately (it polls every
4 s, plus a desktop notification). Nothing goes to GitLab: these threads are private between the user and you.

`merge-train` is on the PATH (`~/.local/bin/merge-train`). `merge-train agent <befehl> --help` lists the options.

## Two rules

1. **Answer in the thread, not in the console.** Every answer to a merge-train message goes through
   `merge-train agent antworten <id> …`. The user reads it at the code line on the page, not in this terminal.
   In the console, at most one line like "3 Fäden in merge-train beantwortet" – never the answer itself.
2. **"Kommentare", "Nachrichten", "Fragen", "Feedback" – even "GitLab-Kommentare" – mean the merge-train
   threads** whenever they arrived via `horchen`/`feedback` or the user talks about what they wrote in merge-train.
   Don't fetch or post GitLab MR discussions (glab, API) for them. Real GitLab review comments are a different
   task (e.g. the `mr-fetch-feedback` skill) and only when the user clearly asks for GitLab itself.

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
merge-train agent antworten <id> "Text" --als Copilot   # only if you were asked under another name
```

- Write in the user's language (German), short and to the point, Markdown-like formatting is fine.
- Refer to code as `pfad:zeile`. Name the commit when you implemented something.
- One `antworten` call per thread – that is the answer; don't repeat it in the console. If a question is unclear, ask back in the thread instead of guessing.
- `--erledigt` only when a request is really done; for a plain answer leave the thread open (the user closes it).

## Writing or adjusting a GitLab comment

Often the user asks in a thread to reword a GitLab review comment (a draft or an agent hint on the MR page), or a
proposal ends in a new comment text. The thread answer itself is German and internal; the **comment text** inside it
is for the MR author and follows the user's GitLab comment conventions:

- Before writing it, read the rules for `text` in `~/.claude/skills/jira-review/SKILL.md` (step 6, "`text` is the final
  English GitLab comment") and apply them, plus the repo's memory on review comments if there is one (e.g. FE findings
  phrased as questions). They win over this summary.
- In short: English, plain and short (usually 2–4 sentences: problem, why it matters, what to do instead), in the tone
  of the user's commit messages.
- **No internal IDs**: no finding IDs (`#8`, `K2`), marker titles, thread or hint ids, nothing that only exists in
  merge-train or the review JSON. The author reads GitLab file by file and can't resolve them.
- Refer to other places **by class or file name**, without line numbers ("same copy as in the CVD handler"); exact
  locations belong in the review JSON's `see_also`, not in the comment.
- Name the proposal, don't spell it out (no full signatures); at most a few technical terms.

**The change goes into the comment, not into the thread.** `feedback`/`horchen` list under each thread the GitLab
comments and agent hints on the same line ("an dieser Zeile: …", with id and full text). Then:

```sh
merge-train agent kommentar h:<key> "New text"      # agent hint not taken over yet: changes its text in the review JSON
merge-train agent kommentar <kommentar-id> "New text"  # existing comment (draft or already in GitLab): new draft next to it
merge-train agent kommentar <faden-id> "New text"    # no comment there yet: new draft at the thread's line
merge-train agent kommentar <ziel> - <<'EOF'         # longer text from stdin
…
EOF
```

- Existing comments are never edited: you add a new draft next to them, the user deletes one of the two.
  Don't delete anything.
- Then answer the thread **very briefly**: "Done" for small things, otherwise one line on what changed (e.g. "Done:
  Finding-ID raus, auf 2 Sätze gekürzt"). Don't repeat the comment text in the thread.
- If it's unclear which comment is meant (several on the line, none listed), ask back in the thread.

## Listen

When the user asks you to listen ("hör auf merge-train", "hör zu"), or after answering when the prompt says so:

1. Start `merge-train agent horchen [MR]` **in the background** (Bash `run_in_background`). The page then shows
   „🎧 Claude hört zu“, and „Feedback/Fragen senden“ goes straight to you. Use `--als <Name>` if you are not
   Claude (e.g. `--als Copilot`).
2. When it exits with messages, its output is the same as `feedback` (already marked as picked up): answer each
   thread with `merge-train agent antworten` (not in the console), then start `horchen` again.
3. It also ends by itself, with exit 1 and a message, when the page has been closed for a while or this agent
   session ends. Then do **not** restart; tell the user listening stopped and that "hör zu" starts it again.

Don't run `horchen` in the foreground (it blocks until the user sends) and don't start several at once for the
same conversation.

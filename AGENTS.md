# Project instructions for AI coding assistants

## Source of truth and repository workflow

- Treat the live GitHub repository `Starv1ng/Kami-no-Eye` as the canonical source of truth for project code, documentation, tests, branches, and current implementation state.
- Before diagnosing a project issue, proposing a code change, or continuing previous work, inspect the relevant files directly in GitHub on the active target branch and verify the latest commit. Check related tests and documentation as needed.
- Do not treat uploaded ZIP archives, copied snippets, screenshots, or local snapshots as the current project state when the repository can be inspected. Use them only when the user explicitly asks to analyze that artifact or when the required material is not available in GitHub; state that limitation clearly.
- Do not ask the user to run searches or paste files merely to discover code that is accessible through the GitHub integration. Use the repository tools first. Ask for terminal output only when runtime behavior, local uncommitted changes, deployment state, or environment-specific diagnostics cannot be established from GitHub.
- Do not assume that the default branch is the branch being developed. Verify the active/relevant branch and its current head before reading or writing files. Preserve the user's current work and avoid overwriting unrelated changes.
- Before changing an existing file, fetch its current contents and blob SHA from the target branch. Keep edits scoped to the task, and verify the resulting commit or diff after writing.

## Engineering and data-safety rules

- Read the relevant implementation, authorization rules, migrations, and tests before changing behavior. Prefer a minimal, coherent fix over an unrelated refactor.
- Add or update regression tests for bug fixes, especially for permissions, shared investigations, session lifecycle, persistence, and graph editing.
- Never weaken authorization checks to work around a user-interface error. Enforce access control on the server and make the interface reflect the effective permissions.
- A read-only/shared investigation must remain read-only, but lack of edit permission must never trap the user in the investigation. Exiting or closing a session must be independent of mutating or restoring protected investigation data. Rejected edit attempts must not prevent navigation away or session closure.
- Treat persisted investigation data as valuable. Never recommend or execute destructive database/volume cleanup (including `docker compose down -v`, volume pruning, or deleting PostgreSQL data) as a routine troubleshooting step. Verify backups and explain data-loss risk before any potentially destructive operation.
- Do not claim a fix is implemented or tested unless the corresponding repository change or test result has actually been verified. Distinguish repository inspection from runtime verification.

## Communication

- Communicate with the user in Spanish unless they request another language.
- When a runtime-only issue cannot be diagnosed from repository contents, explain exactly what cannot be observed remotely and request the smallest relevant command output.

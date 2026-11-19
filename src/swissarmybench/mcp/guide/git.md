# Git (an extension)

When the Git extension is installed (`app_mode(areas=true)` lists the `scm` area), the team library folder and
the shared projects folder sync with GitHub through GitHub's web API: no Git on the computer. Its `github_` tools
sync; its `scm_` tools are the Source Control page (VS Code's Source Control view and graph).

## Signing in
- `github_status`: who is signed in (never the token), each folder (`which`: `library`, the team library folder;
  `shared`, the shared projects folder), its repository and branch and its words: Not connected, Up to date,
  3 changes to push, 2 behind: Pull, Conflicts: 2. `remote=true` asks GitHub (at most once a minute).
- Joining a team is `team_join` (guide topic library). Signing in and out is the user's own (Settings, Team: a token or Sign in with GitHub). You cannot.
- `github_repositories`: the signed-in user's repositories.

## Clone, connect, pull, push (each waits for the user's Allow)
- `github_clone(repository, which, folder?)`: into an empty or new folder, which then becomes that folder.
- `github_connect(repository, which)`: an existing folder linked; nothing written. Pull brings GitHub's files;
  a file different on both sides comes as a conflict.
- `github_pull(which)`: GitHub's changes; a file changed on both sides is merged by lines, else the local
  file stays and GitHub's is saved beside it as `<name>.theirs` (a conflict: the user keeps what they want,
  deletes the `.theirs`, then pushes).
- `github_push(which, message?, path?)`: one commit, fast-forward only; refused while GitHub is ahead (pull
  first) or a conflict waits, or when a file looks like it holds a secret (it names the file). `path`: a shared
  project's folder, only its files. `.gitignore`, `local/`, `.sab/data/` and files over 50 MB never go.

## Source Control (the page; `scm_`)
- `scm_changes(which?)`: each repository's groups: `merge` (conflicts, `!`), `index` (staged), `workingTree`
  (M modified, D deleted, U untracked, A added when staged).
- `scm_stage(paths, unstage?)`, `scm_commit(message, paths?, sync?)` (the staged files, else every change),
  `scm_sync` (pull then push), `scm_discard(paths)` (back to the last synced version: Allow).
- `scm_history(page?)`: the branch's commits (100 a page), refs; `scm_commit_files(commit)`;
  `scm_diff(path, commit?, conflict?)`: unified diff text.
- `scm_branches`, `scm_checkout(branch, create?)` (refused while files here changed; create makes it on GitHub).

No local Git: stash, a local commit before pushing, rebase, amend, staging part of a file, tags and worktrees
are not here (the page shows them disabled).

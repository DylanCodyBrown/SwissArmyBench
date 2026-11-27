# Third-party notices

Swiss Army Bench includes code adapted from the projects below. Each adapted file keeps the project's notice at its
top; this file lists them and carries each licence's text.

## Code - OSS (Visual Studio Code)

<https://github.com/microsoft/vscode>, MIT License. Used by the Git extension's Source Control page (the owner,
2026-11-18: "literally clone to exactly no deviation" of VS Code's Source Control view and graph):

- `web/src/scmGraph.ts`: the graph's swimlanes, ported from `src/vs/workbench/contrib/scm/browser/scmHistory.ts`
  (`renderSCMHistoryItemGraph`, `toISCMHistoryItemViewModelArray`: sizes, curves, circles, the lane colours).
- `web/static/grid.css`, the section "The Source Control page": values ported from
  `src/vs/workbench/contrib/scm/browser/media/scm.css`, `src/vs/base/browser/ui/{button,actionbar,countBadge,
  splitview}/*.css` and the Dark Modern and Light Modern themes (`extensions/theme-defaults/themes`).
- `web/src/lazy/codeEditor.ts` (`createDiffViewer`) and `src/swissarmybench_git/domain/sync.py`
  (`STATUS`): the Modern themes' editor colours, and git's status letters, words and decoration colour keys
  (`extensions/git/src/repository.ts`).
- `web/src/scmPage.ts`: the view's words, menus, letters and codicon code points as VS Code's git extension
  declares them (`extensions/git/package.json`, `package.nls.json`); the codicon font is Monaco's own.

```
MIT License

Copyright (c) 2015 - present Microsoft Corporation

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

No code from the Git Graph extension (mhutchie/vscode-git-graph) is used: its licence does not allow it.

---
name: craft-review
description: Review Swiss Army Bench code for its architecture and craft (Robert Martin's clean architecture, the five SOLID design principles, design smells) when reviewing a change, refactoring, or deciding where new code belongs. Complements ruff, mypy, the tests and tests/test_architecture.py; never replaces them.
---

# Craft review

Adapted for this repository from the community skill "uncle-bob-craft"
(github.com/sickn33/agentic-awesome-skills, skills/uncle-bob-craft), which draws on Robert Martin's *Clean Code*,
*Clean Architecture*, *The Clean Coder* and *Clean Agile*. The project's own rules come first: CLAUDE.md, REFACTOR.md
(the Cosmic Python layers) and the owner's words win over anything here.

These are judgement calls, not laws. Every finding names a file and line or area and the concrete risk of change it
causes ("changing the discount rule means editing four files"), never a principle's name alone. A clean area needs
no finding. Run ruff, mypy and the tests separately; do not repeat what they already catch.

## What to check, in this order

1. **Boundaries and the dependency rule.** Dependencies point inward: `domain/` (standard library and sqlglot only,
   no I/O, no clock) ← `services/` (use cases, given ports) ← `adapters/` and `server/` (the edge). A use case never
   imports a driver, Starlette, a file path or another feature's adapter; it depends on a port the inner layer
   defines, and `bootstrap.py` (the composition root) wires the real one. `tests/test_architecture.py` checks the
   imports; look for what it cannot see: a service doing I/O through a lambda, domain rules living in a route or
   in `web/`, an extension reaching into a base service's internals instead of `hooks.py`, the front end deciding
   what the backend should.
2. **The five SOLID principles, only where they bite.**
   - Single responsibility: one reason to change, one person or role asking for the change. A file or class that
     changes for two unrelated features is two things.
   - Open/closed: a new kind (connection kind, pattern, target, analysis) is added as data or a new module, not by
     editing a growing `if kind == ...` chain in many places.
   - Substitution: every implementation of a port behaves as its callers expect (the stand-ins in tests/ too).
   - Interface segregation: small ports; a service is not handed a whole other service when it needs one call.
   - Dependency inversion: inner code depends on an abstraction it owns; the concrete client arrives from outside.
3. **The seven smells**, each with where it occurs:
   - Rigidity: one small change forces edits across many files.
   - Fragility: a change breaks something unrelated.
   - Immobility: useful code that cannot be reused without dragging its surroundings.
   - Viscosity: the hack is easier than the right way (so the next person will hack too).
   - Needless complexity: abstraction, options or layers nobody uses yet.
   - Needless repetition: the same rule written in two places (it will drift).
   - Opacity: hard to understand what it does or why.
4. **Design patterns.** One is justified by a real problem: repeated variation, hard creation, a cross-cutting concern
   at a boundary. Introduce one at the third duplication or the second reason to change, not before. Warning signs:
   a factory that only constructs, a strategy with one implementation, a layer that only forwards calls, a facade
   hiding a god object.
5. **Tests and care.** The touched code has tests at the right layer (domain rules as pure tests, use cases with
   fakes, a browser test for what a person does); deferred work has its risk said and a place in docs/ideas.md. Do
   not judge the author from a TODO.

## When writing or refactoring

Small, single-purpose functions and modules; business rules in `domain/`, adapters at the edge; one smell at a time,
in small steps, the tests green after each; better names and structure before new behaviour. adapter.py and
api_adapter.py keep their own rules (contract only grows, its own commit, version and change list).

## The report

1. Boundaries: a sentence or two on the dependency direction and any breach, with its file.
2. SOLID: each breach with file or function and the principle, e.g. "Single responsibility: services/x.py both
   plans the export and writes the files; split the writing into adapters/".
3. Smells: each with its place and its cost.
4. The refactors worth doing: one or two per area, each with its risk, its size (small, medium, large) and what it
   buys. Rank across areas by risk reduced per effort.
5. Tests: what covers it, what does not, the risk left.

Write it in plain words, no acronyms beyond names in the code, for the owner to read.

# Project Operating Protocol

This document is pySecretary's persistent operating protocol. Follow it for every non-trivial change. If this protocol conflicts with another active project document, update the documents until the conflict is resolved before implementation.

## Rule 1: Document First

Before writing implementation code, update or create the relevant design document.

Examples:

- KoboldCPP adapter behavior: `docs/modules/koboldcpp.md`
- UI, streaming feedback, and concurrency behavior: `docs/modules/ui.md`
- KoboldCPP runtime assumptions: `docs/deployment/koboldcpp.md`
- Top-level architecture: `docs/DESIGN.md`
- Milestones and active work: `docs/planning/roadmap.md` and `docs/planning/todo.md`
- Test strategy: `docs/testing/strategy.md`

Documentation should define:

- the user-visible goal,
- module boundaries,
- public interfaces,
- data contracts,
- communication protocol,
- error behavior,
- test expectations,
- acceptance criteria.

## Rule 2: Holistic Document Review

After updating design docs, review the active project memory together:

1. `docs/DESIGN.md`
2. relevant `docs/modules/*.md`
3. relevant `docs/deployment/*.md`
4. `docs/testing/strategy.md`
5. `docs/planning/roadmap.md`
6. `docs/planning/todo.md`

The design is green only when:

- no active docs contradict each other,
- the intended module owner is clear,
- the public interface is clear,
- the data exchange shape is clear,
- test layers are identified,
- TODO items point to the correct milestone,
- no obsolete draft remains in the active docs.

If a draft becomes outdated, move it to `docs/planning/archive/` and note what replaced it.

## Rule 3: Update Planning Memory Before Code

When design is green, update planning memory before implementation:

- `docs/planning/roadmap.md`: milestone scope, acceptance criteria, and status.
- `docs/planning/todo.md`: active task list tied to milestones.
- `docs/planning/README.md`: active document index if a new active document was added.

Planning docs should cite the design docs that control the work. TODO items should be actionable and current, not historical notes.

## Rule 4: Implement Against The Documented Interface

Implementation should follow the documented module contract.

Required implementation practices:

- Keep module ownership boundaries clear.
- Do not let downstream modules bypass adapter or controller interfaces.
- Prefer typed dataclasses/protocols for public contracts.
- Use event/command messages for inter-module and UI/backend communication.
- Keep thought/debug data physically and logically separate from final/spoken output.
- Avoid direct cross-thread UI mutation.

## Rule 5: Review Against The Protocol

Before tests are considered final, review the implementation against:

- the relevant design doc,
- roadmap acceptance criteria,
- active TODO items,
- testing strategy layers,
- known deployment constraints.

Review questions:

- Does the code implement exactly the documented interface?
- Does it introduce a new behavior not documented yet?
- Does it bypass a module boundary?
- Does it create stale or contradictory planning docs?
- Does it need archive cleanup?

## Rule 6: Tests Must Match The Design

Tests are part of the design validation, not an afterthought.

Every meaningful implementation should identify which layers it validates:

- Layer 1: API/data-contract tests.
- Layer 2: module behavior tests.
- Layer 3: protocol/communication/inter-module tests.

The required testing details live in `docs/testing/strategy.md`.

## Completion Checklist

A change is complete only when:

- relevant design docs are updated,
- active docs are reviewed holistically,
- roadmap and TODO are updated,
- implementation follows documented boundaries,
- tests cover the relevant layers,
- test command passes,
- compile/static sanity check passes when applicable,
- completed or obsolete drafts are archived,
- final summary cites changed docs and verification.


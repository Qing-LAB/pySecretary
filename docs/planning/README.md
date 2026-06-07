# Planning Directory

This directory is pySecretary's persistent planning memory. Keep active roadmap, TODO, and milestone documents here. Move completed, outdated, or superseded planning drafts into `docs/planning/archive/`.

## Active Documents

- [`protocol.md`](protocol.md): document-first operating protocol.
- [`roadmap.md`](roadmap.md): current milestone plan and acceptance gates.
- [`todo.md`](todo.md): current working task list.
- [`../DESIGN.md`](../DESIGN.md): top-level architecture and module ownership.
- [`../modules/koboldcpp.md`](../modules/koboldcpp.md): KoboldCPP adapter contract.
- [`../modules/app.md`](../modules/app.md): simple synchronous voice loop contract.
- [`../modules/voice_prototype.md`](../modules/voice_prototype.md): automatic voice smoothing prototype contract.
- [`../modules/events.md`](../modules/events.md): event/command/state data contracts and reducer.
- [`../modules/transcript.md`](../modules/transcript.md): thought separation and transcript merge contract.
- [`../modules/context_budget.md`](../modules/context_budget.md): prompt context-window budgeting contract.
- [`../modules/console.md`](../modules/console.md): CLI status indicator contract.
- [`../modules/ui.md`](../modules/ui.md): lightweight UI dashboard, streaming feedback, and concurrency contract.
- [`../deployment/koboldcpp.md`](../deployment/koboldcpp.md): local KoboldCPP runtime contract.
- [`../testing/strategy.md`](../testing/strategy.md): layered testing strategy.

## Memory Map

Use this map when reviewing work holistically:

- Architecture: `docs/DESIGN.md`
- Operating protocol: `docs/planning/protocol.md`
- Active roadmap: `docs/planning/roadmap.md`
- Active TODO: `docs/planning/todo.md`
- Module contracts: `docs/modules/`
- Deployment contracts: `docs/deployment/`
- Test strategy: `docs/testing/strategy.md`
- Archived plans/drafts: `docs/planning/archive/`

## Archive Policy

Use `archive/` for:

- completed milestone snapshots,
- outdated drafts,
- superseded plans,
- investigation notes that are no longer active.

When archiving a document:

1. Move it into `docs/planning/archive/`.
2. Add a short note at the top explaining why it was archived and what replaced it.
3. Remove it from the active document list above.
4. Keep active TODO and roadmap files focused on current work only.

## Update Rules

- Follow [`protocol.md`](protocol.md) for every non-trivial change.
- Update planning docs in the same change as meaningful implementation work.
- Every milestone must have testable acceptance criteria.
- Every task in `todo.md` should point to a milestone in `roadmap.md`.
- If a design decision changes module behavior, update both the relevant design doc and the planning docs.
- Prefer small status changes over accumulating stale notes.

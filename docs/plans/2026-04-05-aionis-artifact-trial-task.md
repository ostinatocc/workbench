# Aionis Artifact Trial Task

## Fixed task prompt

Build a `Stateful Visual Dependency Explorer` for async task orchestration with:

- a graph canvas
- a detail side panel
- a timeline panel
- a search/filter bar
- persistent UI state across refresh

## Product shape

The artifact should feel like a focused internal engineering tool, not a generic landing page.

Required visible structure:

- left or central dependency graph
- right-side detail surface for the selected node
- lower timeline or history view
- top-level search/filter controls

## Fixed scope

Include:

- graph canvas
- detail panel
- timeline panel
- search/filter
- selection state
- persisted selected node and filter state

Exclude:

- auth
- collaboration
- remote sync
- production deployment
- full backend services

## Expected sprint shape

`Sprint 1`

- graph shell renders
- selection updates details
- selection updates timeline

`Sprint 2`

- search/filter is usable
- persistence survives refresh
- the app becomes clearly demoable

## Expected failure points

The trial is considered realistic because at least one of these should be likely:

- graph shell is visually incomplete on first pass
- detail and timeline linkage is partial
- filter/search logic is inconsistent
- refresh loses selected node or filter state
- persistence patch improves one area while regressing another

## What counts as “good enough”

The artifact is considered good enough when:

- a reviewer can run it locally
- the core interaction is understandable in under a minute
- refresh does not destroy the core workflow
- the app looks like a real demo, not a pile of disconnected widgets

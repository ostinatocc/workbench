# Aionis Workbench Design

## Goal

Build a product shell that puts Aionis Core's largest value in front of the user:

- continuity
- shared memory
- delegation
- learning from repeated use
- forgetting of low-signal context

## Product model

Each task is a `WorkbenchSession`.

A session contains:

- `shared_memory`
- `working_memory`
- `delegation_packets`
- `promoted_insights`
- `forgetting_backlog`

The execution substrate is `deepagents`, but the product identity is `Aionis Workbench`, not a raw host wrapper.

## First implementation slice

1. Product CLI
2. Session persistence
3. Built-in specialist roles
4. Delegation packet generation
5. Promotion and forgetting policy
6. Aionis lifecycle + replay integration

## Non-goals for this slice

- UI
- external database
- custom container backend
- distributed coordination

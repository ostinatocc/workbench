# Aionis Artifact Trial Plan

**Goal:** Run one real long-task trial that produces a visible, runnable artifact, so Aionis can be judged by the final product rather than only by benchmark metrics.

**Core thesis:** The next proof step should be `proof by artifact`, not `proof by metric`. The trial must end with two things a human can directly inspect:

- a baseline artifact
- an Aionis artifact

The user should be able to compare the final result without reading internal state or benchmark logs.

**Recommended trial:** `Stateful Visual Dependency Explorer`

**Why this task:**
- naturally spans multiple sprints
- reliably triggers evaluator objections
- strongly exercises retry/replan behavior
- has obvious visible acceptance criteria
- matches the current strengths of Aionis Workbench

**Success criteria:**
- both arms produce a real runnable demo
- both arms are inspected through the same visible checklist
- the output includes screenshots, a short walkthrough, and a final verdict
- the comparison can be made by looking at the artifact, not by reading internal traces

**Out of scope for this trial:**
- browser-grade Playwright QA
- cross-model comparisons
- team workflow/process metrics
- large backends or multi-service deployments

---

### Task 1: Freeze the artifact contract

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-spec.md`

**Step 1: Define the visible deliverable**

The trial must produce:
- one baseline repo/worktree output
- one Aionis repo/worktree output
- one runnable local demo per arm
- one shared comparison checklist

**Step 2: Lock the visible acceptance criteria**

At minimum:
- graph canvas renders
- selecting a node updates the detail panel
- timeline panel updates with the selected node
- filter/search changes graph visibility
- refresh preserves selected node, filters, and timeline focus

**Step 3: Lock the artifact proof package**

Require:
- local run command
- short demo script
- 2-4 screenshots per arm
- a one-page conclusion

---

### Task 2: Define the task exactly once

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-task.md`

**Step 1: Fix the product prompt**

Use one task prompt for both arms:

`Build a Stateful Visual Dependency Explorer for async task orchestration with a graph canvas, detail panel, timeline panel, and persistent UI state across refresh.`

**Step 2: Fix the product scope**

Include:
- graph canvas
- detail side panel
- timeline panel
- search/filter bar
- persistence for selected node and filters

Exclude:
- multi-user sync
- auth
- remote backend
- production polish beyond the visible workflow

**Step 3: Fix the sprint expectation**

Expected path:
- `sprint-1`: graph shell + detail/timeline linkage
- `sprint-2`: persistence and workflow stabilization

---

### Task 3: Create a shared visible review checklist

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-checklist.md`

**Step 1: Create a human-facing checklist**

Check:
- does the graph render
- does node selection work
- does detail view update correctly
- does timeline update correctly
- do filters/search work
- does refresh preserve state
- does the app still feel coherent after persistence changes

**Step 2: Score with simple labels**

Use:
- `works`
- `partial`
- `broken`

**Step 3: Add a short UX judgment line**

For each arm, record:
- what feels solid
- what feels unfinished
- whether it looks demoable

---

### Task 4: Build the baseline artifact run path

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-baseline-runbook.md`

**Step 1: Define the baseline policy**

Keep it intentionally thin:
- one plan
- one implementation attempt
- one evaluator pass
- optional one retry
- no structured replan lineage

**Step 2: Define the artifact boundary**

The baseline arm must still output:
- a runnable project
- screenshots
- checklist results

**Step 3: Prevent hidden hand-tuning**

Use the same:
- provider profile
- model family
- repo fixture
- core prompt

---

### Task 5: Build the Aionis artifact run path

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-aionis-runbook.md`

**Step 1: Use the current app harness**

Allow:
- `plan`
- `qa`
- `negotiate`
- `retry`
- `generate`
- `replan`
- `advance`

**Step 2: Define when the Aionis run is considered complete**

Completion should require:
- a runnable artifact
- a visible persistence workflow
- an artifact judged against the shared checklist

**Step 3: Save the visible proof**

Require:
- final run command
- screenshots
- final checklist
- short operator note about where Aionis actually helped

---

### Task 6: Create a dual-artifact comparison surface

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-report-template.md`

**Step 1: Use a side-by-side format**

The report should show:
- baseline artifact
- Aionis artifact
- screenshot comparison
- checklist comparison
- final verdict

**Step 2: Keep the final verdict concrete**

Answer:
- which one is more runnable
- which one is more complete
- which one is more stable after refresh
- which one looks more demoable

**Step 3: Avoid benchmark-only language**

Prefer:
- `the artifact works`
- `the artifact fails on refresh`
- `the artifact reaches a demoable state`

Not just:
- `winner`
- `delta`
- `convergence signal`

---

### Task 7: Run one deterministic artifact rehearsal

**Files:**
- Modify as needed across trial docs and harness code

**Step 1: Do a dry run with the Aionis arm only**

Goal:
- confirm the task is scoped correctly
- confirm screenshots can be taken
- confirm the checklist is usable

**Step 2: Adjust scope if needed**

If the task is too wide, cut features before the full trial.

**Step 3: Freeze the final prompt**

Do not change the product prompt after rehearsal.

---

### Task 8: Run the real artifact trial

**Files:**
- Create results under a dated trial folder when running

**Step 1: Run the baseline arm**

Save:
- final output
- screenshots
- checklist
- short notes

**Step 2: Run the Aionis arm**

Save:
- final output
- screenshots
- checklist
- short notes

**Step 3: Compare the final product directly**

Judge the artifact, not the state machine.

---

### Task 9: Write the artifact-first conclusion

**Files:**
- Create: `/Volumes/ziel/Aioniscli/Aionis/workbench/docs/plans/2026-04-05-aionis-artifact-trial-status.md`

**Step 1: Record both visible outputs**

Include:
- run command
- screenshots
- checklist result
- final verdict

**Step 2: State the conclusion plainly**

Example:
- `Baseline produced a partial shell that lost state after refresh.`
- `Aionis produced a runnable explorer that preserved selection and filters across refresh and advanced to the next sprint.`

**Step 3: Make the next decision obvious**

Answer:
- is Aionis already good enough for visible long-task demos
- what still blocks a stronger public proof

---

### Task 10: Decide what proof comes next

**Files:**
- Modify the status doc if needed

**Step 1: If the artifact trial is strong**

Promote it into:
- demo video
- homepage proof section
- investor proof point

**Step 2: If the artifact trial is mixed**

Use it to identify:
- generator gaps
- evaluator gaps
- task classes that still need tighter control

**Step 3: Do not go back to abstract claims**

After this trial, the preferred proof should be:
- visible artifact
- runnable workflow
- side-by-side output

not just more internal metrics.

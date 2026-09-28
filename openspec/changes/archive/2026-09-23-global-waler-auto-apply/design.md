# Design

## Context

See [proposal.md](proposal.md) for motivation and scope. The current Global Waler flow already has the required reliability pieces, but they are separated by a manual UI step:

1. Main validates input and asks for confirmation before solving when covered Waler results are manually modified.
2. The Dialog runs `OptimizeWalerGlobal` in a worker and posts completion back to the UI thread.
3. A valid result is stored temporarily in the Dialog until the user presses Apply.
4. Main's existing apply callback stages all selected Waler results through `ProjectResultModel`, snapshots current result metadata, commits once, rolls back commit failures, and treats later UI refresh failures as non-transactional.

`ProjectResultModel` remains the single source of truth for committed Solver results. The Dialog may retain the latest solve result only for presentation; it must not become a second authoritative result store.

## Goals / Non-Goals

**Goals:**

- Connect valid worker completion directly to the existing apply callback on the UI thread.
- Keep staging, commit rollback, dirty/calculated-time updates, material summary refresh and preview refresh on their existing ownership boundaries.
- Give the Dialog explicit presentation states for solve failure, apply failure, applied-with-refresh-warning and fully applied.
- Make one solve completion produce at most one apply attempt.

**Non-Goals:**

- Moving result commit into the worker thread or optimization use case.
- Changing Global Waler candidates, exact DP, objective ordering, diagnostics or summary calculations.
- Introducing a new transaction service or persistence schema.
- Changing Single Waler behavior or the meaning of manual result modification.

## Architecture Alignment

This change follows the existing architecture rather than changing it:

- **Algorithms** continue to own Global Waler calculation only and remain unaware of UI or `ProjectResultModel`.
- **Application** continues to own staged result construction through the existing `ProjectResultModel` contract.
- **Presentation/Main orchestration** continues to decide when a valid Solver result is adopted, execute the existing commit boundary, and refresh widgets.
- Dependency direction remains Presentation → Application → Algorithms/Domain. No reverse dependency or new persistence dependency is introduced.

The only long-term truth that changes is the Global Waler workflow commit timing. `docs/WORKFLOW.md` must be updated after implementation and verification; `docs/ARCHITECTURE.md`, `docs/DOMAIN.md`, and `docs/SOLVER.md` do not require behavioral changes.

## Decisions

### 1. Auto-apply from the Dialog's UI-thread completion path

When worker completion reaches the Dialog and the returned solution is valid, the Dialog will first populate the result rows and base summary, then invoke the existing apply callback exactly once. This preserves the current UI-thread boundary and lets the user see the computed solution even if commit fails.

The manual Apply button and pending-apply interaction will be removed. The Dialog may retain `current_result` for summary/display and `open()` compatibility, but that value is not committed state and closing the Dialog performs no mutation.

**Alternative rejected:** Keep the button and programmatically call its command. This retains misleading pending-state UI and makes duplicate application easier to trigger.

**Alternative rejected:** Apply inside the worker or `OptimizeWalerGlobal`. This would mix UI/application state mutation into the algorithm workflow and risk Tk operations outside the UI thread.

### 2. Reuse the existing apply callback and outcome contract

The Dialog will not duplicate staging or rollback logic. It will call Main's existing global apply callback and interpret its outcome as follows:

- `committed=False`: show apply failure, state that original results were preserved, and do not label the solution as adopted.
- `committed=True, refreshed=False`: label the result as adopted, retain it as formal state, and warn that the UI refresh failed.
- `committed=True, refreshed=True`: label the result as adopted and show the successful summary.

An unexpected callback exception is treated like apply failure because the Dialog has no evidence of a successful commit. The authoritative callback must continue returning an outcome after handling its known staging, commit and refresh boundaries.

**Alternative rejected:** Roll back after a refresh error. Refresh is outside the transaction and the committed `ProjectResultModel` is more authoritative than widget state; rolling back would conflate data and presentation failures.

### 3. Preserve the existing atomic commit boundary

`ProjectResultModel.stage_waler_global_result()` continues to build a complete replacement mapping without mutating current state. Main continues to snapshot `result_items`, persisted result metadata, calculated time and dirty metadata before adopting the staged mapping. A staging or commit error therefore leaves all Waler and non-Waler results in their original state.

The successful post-commit refresh sequence remains owned by Main: refresh the result tree (which also refreshes material statistics), select the results area, update Preview, and display the global summary. No new partial per-Waler writes are introduced.

### 4. Keep overwrite consent at the pre-solve boundary

The existing Main preflight remains before Dialog construction and before worker acquisition. It examines all Waler inputs covered by the proposed run and asks once when any corresponding result is marked `manual_modified`. Declining returns before the Solver starts.

No second overwrite prompt will be added after solving, because consent has already been obtained and the new workflow commits immediately when a valid solution arrives.

### 5. Present adoption state as part of the result summary

The existing S/M/L/O, target/actual ratios, deviation, Out distance, local regret and changed-Waler details remain derived from the Solver result/diagnostics. The Dialog will add an explicit adoption status instead of recomputing any engineering values.

After commit success, closing the Dialog only destroys presentation state. There is no Cancel/undo path because the formal result has already been committed; later replacement or editing uses existing result workflows.

## Risks / Trade-offs

- **[Risk] The apply callback is accidentally invoked more than once for one completion event.** → Keep auto-adoption in one completion path, remove the Apply command, and add a callback-count regression test.
- **[Risk] A callback exception occurs after an unreported commit.** → Preserve the existing callback outcome boundary and tests; known commit/refresh failures must be converted to explicit outcomes rather than escaping.
- **[Risk] The user sees a valid computed solution that failed to commit and assumes it is active.** → Use distinct summary/status text and never show「全域結果已採用」when `committed` is false.
- **[Risk] Refresh failure leaves widgets stale.** → Warn that the result is already adopted and preserve committed data; the user may close/reopen or trigger a later refresh without data rollback.
- **[Trade-off] A valid result can no longer be inspected and discarded before adoption.** → This is intentional and matches the requested immediate-commit workflow; overwrite consent remains before the potentially expensive solve.

## Migration Plan

No data or Project schema migration is required.

1. Add regression coverage for automatic adoption and Dialog outcome states.
2. Replace the Dialog's valid-result pending state with immediate callback invocation and remove the Apply control/path.
3. Preserve and re-run existing atomic apply/rollback tests in Main and `ProjectResultModel`.
4. Update `docs/WORKFLOW.md` only after verified implementation so current behavior documentation no longer describes a manual Apply step.

Rollback consists of restoring the prior Dialog interaction code; persisted projects remain compatible because result payloads and schema do not change.

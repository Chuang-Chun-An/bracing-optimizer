# Design

## Context

See [proposal.md](proposal.md) for motivation and scope, and [spec.md](specs/unsaved-changes-navigation-guard/spec.md) for the behavioral contract.

Current code discovery:

- `SupportInputApp._new_project()` and `_load_selected_project_case()` each contain their own dirty check using `messagebox.askyesno`; `True` currently means discard and continue, while `False` means stay.
- `_save_current_project()` routes an unnamed Project to `_save_project_as()` and an existing Project to `save_project_case()`. Both currently return a saved `Path` on success and `None` for multiple distinct outcomes, including user cancellation and handled failure.
- `save_project_case()` calls `ProjectService.save_project()` and only adopts the returned asset/path/payload state and clears dirty after the Application service succeeds. The Infrastructure save is already staged and atomic.
- Open is not a file picker: `_load_selected_project_case()` reads the current project-case selector, rejects an empty selection, then calls `load_project_case()`. `ProjectService.load_project()` fully validates and hydrates before Main adopts the new Project.
- Close already offers Save／Discard／Cancel through `askyesnocancel`, but consumes the ambiguous `Path | None` save return. Its visible behavior is outside this change.
- Manual editing commits immediately into `ProjectResultModel` and marks the Project dirty. This change protects that committed in-memory result during navigation but does not alter the manual-edit commit boundary.

## Goals / Non-Goals

**Goals:**

- Give New and Open one shared, testable dirty-navigation decision boundary.
- Represent save completion as an explicit result rather than overloading `None` or truthiness.
- Keep every destructive New/Open mutation after the guard authorizes continuation.
- Reuse current Save, Save As, ProjectService and persistence transactions.
- Preserve current state exactly when the user cancels or persistence fails.

**Non-Goals:**

- Moving Tk dialogs into Application or Infrastructure.
- Creating a generic navigation framework or command bus.
- Adding a file picker for Open, autosave, undo, schema migration or a second save implementation.
- Changing dirty-state production, manual-edit semantics, Close choices or load adoption behavior.

## Architecture Alignment

This change follows the existing Architecture; it does not introduce a new dependency direction.

- **Presentation (`main.py` and, if useful, one small presentation-only outcome module):** owns the Save／Discard／Cancel prompt, maps the tri-state UI response to named decisions, invokes the save command, and gates New/Open continuations.
- **Application (`ProjectService`):** remains the owner of save/load use-case coordination and successful `SaveProjectResult`／`LoadProjectResult` contracts.
- **Infrastructure:** continues to own staged file writes, validation and atomic replacement; no changes are expected.
- **Domain／Algorithms:** remain untouched.

Dependency direction stays Presentation → Application → Infrastructure. Presentation does not infer persistence success from the chosen button: only a successful return from the existing Application save flow becomes `saved`; a cancelled UI flow becomes `cancelled`; a caught persistence failure becomes `failed` after the existing error presentation.

The authoritative Project input and results remain `ProjectDataModel` and `ProjectResultModel`. The guard stores no second Project snapshot or durable state; its outcome is temporary control-flow state only.

## Decisions

### 1. Introduce explicit save and guard outcomes

Use small enum/dataclass-style values for:

- save status: `saved`, `cancelled`, `failed`;
- navigation guard result: `proceed` or `cancelled`;
- optionally the user decision: `save`, `discard`, `cancel` when that makes the mapping clearer.

A successful save outcome may carry the saved path; a failed outcome may carry diagnostic text for tests/logging, while the existing UI layer remains responsible for showing the error. Callers compare named statuses, never raw truthiness.

These are workflow/presentation outcomes, not persisted Project data and not Domain entities. They should live in a small presentation-level module or immediately adjacent to Main without adding a framework. `ProjectService.save_project()` should keep its current success DTO and exception contract because it cannot observe UI cancellation.

**Alternative rejected:** Add `CANCELLED` to `ProjectService.save_project()`. Cancellation happens before the service is called and would incorrectly mix Tk interaction into the Application persistence contract.

**Alternative rejected:** Continue returning `Path | None` plus checking dirty state. It cannot reliably distinguish cancellation from failure and keeps destructive continuation dependent on incidental side effects.

### 2. One shared dirty-navigation guard for New and Open

Add one Main orchestration helper with this state table:

| Project state / decision | Action | Guard result |
| --- | --- | --- |
| clean | no prompt, no save | proceed |
| dirty + Save + saved | run existing Save/Save As | proceed |
| dirty + Save + cancelled | no continuation | cancelled |
| dirty + Save + failed | show existing save error, no continuation | cancelled |
| dirty + Discard | no save | proceed |
| dirty + Cancel | no save | cancelled |

The helper must not receive or execute New/Open mutation code. Each entry point asks the guard first and calls its existing continuation only on `proceed`. This keeps common policy centralized while leaving destination-specific behavior separate.

The prompt can reuse the established `askyesnocancel` presentation pattern, with explicit semantic mapping Yes → Save, No → Discard, Cancel → Cancel and message text that explains the choices. A custom modal is unnecessary unless implementation testing shows the platform cannot communicate those semantics clearly.

**Alternative rejected:** Duplicate tri-state handling in `_new_project()` and `_load_selected_project_case()`. That recreates the drift already present in the two `askyesno` branches.

**Alternative rejected:** Pass a destructive callback into the guard. Keeping the guard decision-only makes it straightforward to prove no continuation ran before save success.

### 3. Make save commands produce the explicit outcome without duplicating persistence

Refactor the existing Save／Save As orchestration so all paths terminate in one explicit outcome:

- Save As dialog cancelled, empty/invalid name, or overwrite declined → `cancelled`.
- `save_project_case()` returns a path after `ProjectService.save_project()` succeeds → `saved`.
- Existing caught save exception and error dialog → `failed`.

The normal menu commands and navigation guard reuse this same implementation. The compatibility helper `_save_current_project_case_from_prompt()` may project the new outcome back to its legacy `Path | None` shape only if current tests/extensions require it; it must not contain a second save implementation.

Because Close currently invokes `_save_current_project()`, it must be adjusted to compare the explicit save status if that method's return type changes. This is a compatibility adaptation only: Close keeps the existing Save／Discard／Cancel prompt and termination behavior, and is not routed through the New/Open guard.

### 4. Validate an Open target before asking about unsaved changes

`_load_selected_project_case()` continues to resolve the selected project name before invoking the dirty guard. If no valid target is selected, it shows the existing warning and returns without a dirty prompt or save attempt.

The requirement mentioning cancellation of Open target selection is implemented against this actual selector-based UI. This change does not add a file dialog. If a future Open entry point adds a chooser, cancelling it must follow the same pre-guard early-return rule.

### 5. Establish explicit destructive continuation seams

Open already has a clear continuation, `load_project_case(project_name)`, whose hydrate-before-adopt behavior protects current state on load failure.

For New, move the existing reset body behind a small destination-specific helper if needed so tests can assert that it was not called on Save cancellation/failure and was called exactly once after Save success or Discard. The reset sequence itself—new `ProjectDataModel`, cleared `ProjectResultModel`, DXF state/cache reset, UI refresh and dirty clear—must remain behaviorally unchanged.

Tests must capture identity/value snapshots for Project input, committed results, dirty flag/reason, current path and representative UI selection before cancelled/failed flows, then compare them afterward. They must also mock or spy on the destructive continuation, not merely assert prompt wording.

### 6. Preserve existing persistence and manual-edit boundaries

No save operation clears dirty until `ProjectService.save_project()` returns successfully. No Open operation adopts state until `ProjectService.load_project()` returns a fully hydrated result. The guard relies on these current transaction boundaries rather than adding rollback around partially destructive navigation.

Manual Support/Waler edits continue to commit immediately and mark dirty. Their results remain ordinary committed in-memory state protected by the same navigation guard; no manual-edit code or Solver rule is copied into the new workflow.

## Risks / Trade-offs

- **[Risk] Changing private save return types breaks Close or compatibility tests.** → Update every current caller together and retain a thin legacy projection only where evidence requires it.
- **[Risk] The UI's Yes／No labels are less explicit than Save／Discard.** → Use clear prompt copy documenting the mapping; introduce a small custom dialog only if an acceptance test demonstrates that explicit labels are mandatory on the supported platform.
- **[Risk] Save As success changes current path/selector before a later Open load fails.** → This is correct: the current Project was successfully saved. The subsequent load remains independently atomic; tests distinguish save success from target-load failure.
- **[Risk] Tests pass by checking dialog return values without proving safety.** → Assert continuation call counts and full current-state preservation on cancelled/failed paths.
- **[Trade-off] Close does not share the New/Open guard.** → Close already has distinct shutdown cleanup and an accepted prompt; it shares only the explicit save outcome to avoid expanding visible scope.

## Migration Plan

No Project data or file migration is required.

1. Characterize current Save／Save As, New/Open destructive continuations, Close consumption and failure preservation.
2. Add the explicit outcome types and adapt existing save callers.
3. Add the shared New/Open dirty guard and place both continuations behind it.
4. Run focused persistence/navigation/manual-edit tests, then the full regression and architecture boundary suite.
5. After behavior is verified, update `docs/WORKFLOW.md` to make Save／Discard／Cancel the current New/Open behavior and remove the corresponding product-gap entry.

Rollback restores the previous Main orchestration only; saved Project files remain compatible because neither schema nor persistence format changes.

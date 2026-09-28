# Design

## Context

See [proposal.md](./proposal.md) for motivation and scope. Phase 1 currently gives `ProjectService` an exact-only evaluate/commit contract: it validates the paused Review lifecycle, source fingerprint and Review-state token, while `main.py` atomically adopts the returned serialized state. `DXFReviewWorkflow` owns the live DXF Review state, recognition, derived associations, confirmation validity and Review-state serialization. Its normal resume path intentionally rejects a mismatched fingerprint.

The existing `DxfCompatibilityChecker` already contains useful same-role line matching primitives, but its public `compare()` contract is for completed Project relink: it requires critical component counts to remain equal and validates Solver rows. Changed-content paused Review has different semantics: candidate additions are allowed, no Project/Solver rows are applied, and the result must remain in `REVIEW`. Therefore its completed-Project decision cannot be reused directly.

Existing manual recovery helpers are source-identity based. `replay_manual_overrides`, double-support identity helpers and confirmation signature validation can be reused after old identities are safely rebound. `ExcludedSource` does not always contain enough geometry to infer a replacement handle, so exclusions without an exact surviving source identity cannot be guessed.

## Goals / Non-Goals

**Goals:**

- Preserve the existing SHA-256 Exact Match path without extra recognition or confirmation.
- Build changed-content recovery in an isolated candidate state and commit it only after an explicit user decision.
- Make the candidate recognition result the only engineering basis of the recovered Review.
- Rebind and replay only state that can be proven safe, with one summary contract for preserved, requires-review and disabled items.
- Keep candidate fingerprint, paused Review base state and runtime cache adoption within the existing atomic Relink boundary.
- Keep current Project schema and Review state version.

**Non-Goals:**

- Weakening the normal `DXFReviewWorkflow(..., resume_review=True)` fingerprint guard.
- Adding manual component-mapping UI for missing or ambiguous Waler, Strut or Brace matches.
- Reusing paused Review recovery to modify formal Project geometry or Solver state.
- Changing geometry matching tolerances, DXF recognition rules, Review-state schema or managed-copy save behavior.
- Creating another DXF editor or moving existing Review editing behavior into Main.

## Architecture Alignment

This change **uses the existing architecture; it does not change the architecture itself**.

| Layer / subsystem | Responsibility in this change |
| --- | --- |
| Presentation (`main.py`, existing DXF dialog) | Select candidate, show recovery summary, collect explicit acceptance, invoke commit, atomically swap UI runtime references, and resume the existing Review workspace. |
| Application (`ProjectService`) | Validate workflow/fingerprint/base-state token, represent exact versus compatible plans, revalidate at commit, and return one adoption result. It does not perform Tkinter interaction or infer DXF engineering relationships. |
| DXF import subsystem | Re-recognize the candidate, perform Review-specific member matching and identity rebinding, replay eligible Review decisions, rebuild derived state, and produce a data-only recovery stage and summary. |
| Infrastructure | Continue providing file metadata, SHA-256, parseability and existing geometry-match primitives. Managed-copy replacement remains part of Save, not Relink. |
| Domain / Algorithms | No responsibility or dependency change. Formal Project engineering rules and Solver behavior remain untouched. |

The dependency flow remains Presentation → Application for lifecycle/commit coordination and Presentation/Application → DXF import/infrastructure boundaries already used by the brownfield workflow. DXF matching and replay logic must not be implemented in Tkinter callbacks. Domain and Algorithms receive no dependency on DXF or Presentation.

## Decisions

### 1. Keep Exact Match and changed-content recovery as separate paths

`evaluate_paused_review_relink()` remains the entry point for file and lifecycle validation. Exact fingerprint equality continues producing the current exact plan. A valid mismatched fingerprint produces a recovery seed containing the normalized candidate path/fingerprint and base-state token; it does not mutate saved state and is not itself an acceptable plan.

The DXF subsystem consumes that seed and produces either:

- an incompatible/validation result with reasons; or
- an immutable compatible recovery plan plus a runtime recovery stage.

The compatible plan carries the candidate path/fingerprint, original base-state token, recovered serialized Review state and recovery summary. The runtime stage carries the newly recognized `world_result` needed to resume the same-session Review. The runtime result is not persisted as a new schema field.

This separation keeps exact relink fast and prevents a content mismatch from silently becoming an accepted state.

**Alternative rejected:** change Phase 1 so every candidate is re-recognized. This would alter Exact Match behavior, introduce unnecessary failure modes and invalidate decisions that are already known to belong to identical bytes.

### 2. Add one Review-specific pure recovery planner in `dxf_import`

A small non-UI recovery module in `dxf_import` will own data contracts and pure orchestration for:

1. selecting reusable Review settings;
2. recognizing the candidate in isolation;
3. matching saved versus candidate critical members;
4. rebinding eligible source identities;
5. replaying manual state and decisions;
6. rebuilding derived state and validation;
7. serializing the recovered Review state and summary.

It will reuse `DXFImporter`, existing recognition/rebuild functions, `replay_manual_overrides`, double-support helpers and confirmation validation. It may extract the line/handle matching primitive currently embedded in `DxfCompatibilityChecker`, but it must not call the completed-Project `compare()` decision unchanged because that decision rejects candidate additions and includes Solver-row validation.

The existing `DXFReviewWorkflow` stays the owner of live Review mutations. Recovery creates a fresh candidate-based workflow/result through a dedicated factory/planning path; it does not pretend a mismatched source is a normal resume.

**Alternative rejected:** put matching and state reconstruction in `main.py` or the dialog. That would duplicate DXF semantics in Presentation and make headless tests difficult.

**Alternative rejected:** create a general repository/port hierarchy for this feature. The current file and Review boundaries are sufficient; a new broad abstraction would exceed the change.

### 3. Candidate recognition is authoritative after compatibility is proven

For a mismatched source, the planner first creates a fresh candidate result. Saved layer roles are reused only for layer names that still exist and whose classification remains valid; each reused classification is `preserved`. Missing saved layers and previously unseen candidate layers are `requires_review`; unseen layers keep the existing safe unclassified/ignored behavior until the user reviews them. Saved import mode and coordinate system are `preserved` only if their existing validators accept them in the candidate context. Otherwise they are not forced onto the candidate: the candidate uses the existing safe/default behavior and the setting is `requires_review`.

Candidate points, associations, validation messages, double-support candidates and other derived structures are rebuilt from the candidate. They are never copied from the saved `converted` payload.

The recovered serialized state is generated through the existing Review-state serializer, retaining Review state version 2. Recovery-plan metadata and summary stay transient.

**Alternative rejected:** patch the old serialized `converted` data with a new path/fingerprint. That would create a new-source/old-recognition mixed truth and could hide geometry changes.

### 4. Critical-member compatibility is an injective, same-role match

Every saved Waler, Strut and Brace must map to exactly one unused candidate member of the same role. Matching reproduces the current `DxfCompatibilityChecker` primitive rather than inventing a new order:

1. consider only unused members of the same role whose engineering-line error is within the existing `DXF_GEOMETRY_TOLERANCE_MM` boundary;
2. within that geometry-qualified set, rank shared normalized source handle first, same source layer second, and changed source layer third;
3. within the same evidence priority, rank by geometry error;
4. use the existing `DXF_AMBIGUITY_TOLERANCE_MM` rule to reject alternatives at the same best priority whose errors are equally good.

The mapping is injective: one candidate member cannot satisfy multiple saved members. Missing or ambiguous saved members reject recovery. Candidate-only members are accepted as additions and reported as `requires_review`.

No new numeric tolerance is introduced. Tests will use the existing tolerance constants, including their accepted and rejected boundaries.

**Alternative rejected:** require equal Waler/Strut/Brace counts as completed Project relink does. Paused Review is explicitly the place where candidate additions can be reviewed before Project completion.

**Alternative rejected:** automatically choose the nearest member in an ambiguity. A plausible but unproven match could transfer engineering decisions to the wrong component.

### 5. Rebind first, then use existing replay and validation helpers

The critical-member map is converted into an old-source-identity → candidate-source-identity map. Saved manual overrides targeting mapped members are copied with the candidate handles and then passed through `replay_manual_overrides`. Its current success/failure report feeds the common recovery summary.

Other saved state follows these rules:

- **Material:** rebind only through a unique critical-member map, then replay with current validation. Replay success is `preserved`; replay failure is `requires_review`.
- **Manual endpoint:** rebind only through a unique critical-member map, then replay with current validation. Replay success is `preserved`; replay failure is `requires_review` and candidate-based geometry remains active.
- **Waler contact input:** rebind only through a unique critical-member map, then replay with current validation. Replay success is `preserved`; replay failure is `requires_review` and candidate-based contact state remains active.
- **Source exclusion:** preserve only when the exact excluded source identity still exists in the candidate and remains valid for the same role. A geometry-only critical-member rebind never transfers an exclusion. Because persisted `ExcludedSource` has no reliable source engineering line for a changed-handle match, a non-surviving exact identity is `disabled`; the exclusion is summary-only and candidate recognition proceeds without its effect.
- **Double-support decision:** `preserved` only when both Struts map uniquely and the newly detected candidate pair has one matching identity. Every other case is `requires_review`; the old decision is not retained as effective state.
- **Confirmation:** retain as `preserved` only when accepted by existing candidate current-state signature validation. A changed signature removes the confirmation and is `requires_review`.

Associations and validation are always rebuilt after replay. No recovery-specific second implementation of those rules is allowed.

**Alternative rejected:** preserve all handle-keyed state after a geometry match. Handles are part of the current identity contract; blind preservation would make exclusions and decisions target unrelated entities.

### 6. Use one structured recovery summary contract

The recovery planner produces entries with:

- category: `preserved`, `requires_review` or `disabled`;
- subject kind and display label;
- reason code and user-facing description.

Counts are derived from entries rather than maintained separately. Matching facts, new/missing layers, candidate-only critical members, manual replay, exclusions, double-support decisions and confirmations all contribute to the same summary. Presentation formats this contract but does not recalculate recovery meaning.

The three categories are mutually exclusive, and each entry has exactly one category:

- `preserved`: old manual state was safely replayed into the candidate-based recovered Review and remains valid in the recovered state;
- `requires_review`: an actionable candidate-based engineering subject remains, but the old decision, setting or confirmation is not valid; the recovered Review retains the candidate state and requires the user to inspect, set or confirm it again;
- `disabled`: the old manual decision must not affect recovered engineering state and survives only as a summary record explaining why it was not applied.

The fixed classification table is: successful material/manual-endpoint/Waler-contact replay, surviving exact exclusion identity, valid double-support decision and valid confirmation → `preserved`; failed material/manual-endpoint/Waler-contact replay, invalid double-support decision, invalid confirmation, candidate-only critical member, missing/unseen layer, and invalid coordinate/import setting → `requires_review`; non-surviving exact exclusion identity, including a geometry-only critical-member match → `disabled`.

An empty category is still shown with count zero so acceptance is explicit about what changed. Exact Match does not create this summary.

**Alternative rejected:** concatenate messages independently in Main and the dialog. That would create two interpretations of recovery outcome and make tests dependent on UI text.

### 7. Explicit acceptance precedes a guarded atomic commit

Compatible recovery requires a distinct user action after the summary is shown. Rejecting or closing the prompt discards the stage. Selection of the file is sufficient only for Exact Match.

On acceptance, `ProjectService` revalidates:

- workflow is still `REVIEW`;
- current serialized Review-state token equals the plan base token;
- candidate path remains readable and its fingerprint equals the plan fingerprint.

It then returns a compatible adoption result. Main extends its existing rollback snapshot so one atomic adoption covers the candidate source reference, recovered serialized Review state, candidate `world_result` runtime cache, dirty state, recovery/asset reports and every field already protected by the current rollback snapshot. The candidate source reference is adopted only as part of the recovered serialized state/report transition; it is never written ahead of that transition. If any assignment or UI refresh fails, all captured fields are restored, including `dxf_last_import_debug`, `dxf_asset_status_report`, compatibility/recovery reports, dirty flag/reason and `dxf_review_session`, so no candidate-source/old-state or old-source/recovered-state mixed truth remains.

The old same-session `world_result` is never reused across fingerprints. Project geometry and all Solver state remain untouched because Review completion is not invoked.

**Alternative rejected:** write candidate state into `dxf_last_import_debug` before confirmation to simplify preview. This would make Cancel observable and could mix old and new cache/state.

### 8. Persistence and managed-copy behavior remain unchanged

After accepted recovery, the Project becomes dirty for the same reason as Phase 1: the new source relationship and Review state are not yet saved. Existing Save persists the recovered version-2 Review state and updates the managed DXF through the existing transaction. Relink itself does not copy or overwrite the managed asset.

Projects created before this change remain readable. No migration or fallback inference is added for saved Review states that lack `source_fingerprint`; they continue to fail validation safely.

## Single Sources of Truth

- Before acceptance: the currently loaded paused Review state and its source fingerprint are authoritative; the recovery stage is disposable.
- After successful commit: the recovered serialized Review state is authoritative for persistence, and the candidate-derived `world_result` is its same-session cache.
- Candidate engineering geometry and associations come only from the candidate recognition result.
- Recovery classification comes only from the structured summary produced by the DXF recovery planner.
- Formal Project data remains unchanged until the existing Review completion/apply flow runs.

These boundaries prevent the old Review payload, candidate result and formal Project model from becoming competing truths.

## Risks / Trade-offs

- **[Risk] Geometrically repetitive drawings may yield ambiguous matches.** → Reject recovery and require a fresh Review/import; do not add a guessing UI in this phase.
- **[Risk] Source exclusions with changed handles cannot be safely rebound because their persisted form has no reliable source engineering line.** → Preserve only a surviving exact identity for the same role; otherwise classify the exclusion as `disabled`, do not apply it, and report the loss explicitly.
- **[Risk] Candidate-only layers defaulting to ignored can omit new engineering objects from the first staged recognition.** → Report every unseen layer and resume in Review so the user can classify it and rerun existing recognition before completion.
- **[Risk] Replaying Waler contact or manual geometry can alter downstream Strut/Brace geometry and invalidate confirmations.** → Use existing replay/rebuild order and validate confirmations only after all replays and associations finish.
- **[Risk] File or Review state can change while the summary is open.** → Recheck both fingerprint and base-state token at commit and reject stale plans.
- **[Risk] Main owns the final multi-field UI-state swap in the current brownfield design.** → Extend the existing narrow adoption helper and rollback tests; do not introduce a second transaction mechanism.
- **[Trade-off] Candidate additions are permitted but not auto-confirmed.** → This supports common drawing evolution while intentionally returning more items to Review.

## Migration Plan

1. Add Review-specific recovery data contracts, matching/rebinding logic and headless tests without wiring the UI.
2. Extend the existing Application evaluate/commit contract while retaining Phase 1 enum/result behavior for Exact Match call sites.
3. Integrate the existing DXF Review dialog/workflow with staged candidate recovery and structured summary.
4. Extend Main adoption/rollback and resume wiring, then add interaction tests for accept, reject, retry and stale commit.
5. Run Exact Match, Save/Load, Review workflow, Project persistence, architecture-boundary and broader regression tests.
6. After implementation is verified, update `docs/WORKFLOW.md` from exact-only truth to the implemented compatible-recovery truth.

Rollback is code-only: remove the compatible branch and retain the current Exact Match branch. Because the persistence schema is unchanged, no data rollback or migration is required.

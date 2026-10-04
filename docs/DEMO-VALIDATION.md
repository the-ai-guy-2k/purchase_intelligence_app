# Isolated synthetic operator demo — validation

## Scope and start forecast

Baseline: main at b48dd9bd0d500c52c6478b12efa97e03c06cf51d, clean product tree.
Bounded branch: feature/demo-data-existing-fixtures.
No publishing, main merge, personal data, new framework, storage migration,
new dependencies, or live AI requests are part of this work.

The implementation uses a dedicated development startup command, separate demo
storage, a visible label, and the existing grounded test provider. Normal and
published startup remain on run.py. Only the managed development preview
configuration selects run_demo.py.

## Existing sources reused without changing them

- tests/test_purchase_analytics.py:
  test_repeated_item_frequency_quantity_and_trace and _milk.
- tests/test_visual_recall.py:
  test_walmart_food_recall_uses_representative_or_text.
- tests/test_receipt_extraction.py: receipt_png image renderer.
- tests/test_purchase_confirmation.py: confirmation_body.
- tests/live_mvp_validate.py: prepare's Need classification correction.
- tests/test_purchase_memory.py:
  test_confirmed_purchase_becomes_recallable_history's Want correction.
- tests/test_ai_intelligence.py: RecordingProvider.

Existing fixture fields are read from the two named test functions, not copied
into a manually invented dataset. The legacy analytical test helper directly
inserts purchases with synthetic extraction references, so that writer is not
used. Seven corresponding fixture receipt images are rendered with the existing
helper, preserved through normal intake, parsed from their exact synthetic
source text, and explicitly confirmed through the normal endpoint.
Every purchase therefore has original image bytes, an extraction, and valid
source-line references. No OCR or model generation is needed for known source
text. UUIDs/timestamps vary on reset; the semantic fixture contents are stable.

## Demo contents

- 7 confirmed purchases, 12 item records, 8 normalized item identities.
- Merchants: North Market (4), Corner Shop (2), Walmart Supercenter (1).
- Dated records: March 1–26, 2026; one explicitly undated fixture.
- Repeats: Milk Gallon (4 purchases) and Banana (2 purchases).
- Milk intervals: average 12.5 days; latest 15 days.
- Food: 10 item records; non-food: 2.
- Need / Want / Unknown: 4 / 1 / 7.
- Consumable / long-term: 10 / 2.
- Walmart recall: 3 representative-image entries and 1 text-only entry.
- No exact-product-image claim or current-inventory claim is introduced.

## Acceptance results

| Case | Result | Evidence |
| --- | --- | --- |
| 1 Demo load | PASS | Dedicated startup; populated API and visible Overview |
| 2 Real storage isolation | PASS | All normal files retained identical SHA-256 hashes |
| 3 Overview | PASS | Cards, recent purchases, repeat counts and merchant counts render |
| 4 Purchase History | PASS | Seven purchases across dates and merchants |
| 5 Patterns | PASS | Repeats, intervals and classification counts verified |
| 6 Food Recall | PASS | Representative SVG images and text-only entry |
| 7 Ask AI | PASS | Four supported questions return grounded test-provider answers |
| 8 Demo label | PASS | DEMO DATA banner on all six HTML pages |
| 9 Exit/reset | PASS | Normal app remains unlabelled/separate; reset and reuse verified |
| 10 No personal data | PASS | Named synthetic fixtures only; uploads/mutations rejected |

Additional guard tests reject normal-directory overlap, unowned directories and
symlinks before reset. Receipt-image hashes and extraction/source-line lineage
are verified. Asking questions does not modify demo storage.

Focused verification: 24 passing tests (10 demo tests + 14 existing dashboard
tests). One initial middleware-registration issue and one test response-field
assertion were corrected before the final passing run. No complete regression
run was performed because existing product core and normal startup are unchanged.

Live development checks: six pages HTTP 200, representative images HTTP 200,
demo CSS HTTP 200, forbidden upload HTTP 403, four grounded questions ready.
Normal storage hashes still match the pre-demo snapshot.
Visual checks cover Overview, History, Patterns, Food Recall and phone-width Ask.

## Operation and limits

Activate: python run_demo.py from the product directory.
Reset: stop demo, then python run_demo.py --reset.
Exit: stop demo and use the original python run.py command.
Managed commands are artifact-relative:
python purchase_intelligence_app/run_demo.py or
python purchase_intelligence_app/run.py.

Demo-only storage: demo_data/, ignored by Git. Reset deletes only a marked,
owned, non-overlapping demo directory. Normal data/ is not touched.
The test adapter is explicitly labelled; this is not a real-model validation.
Development/test dependencies were already installed and listed.

Real AI calls: 0. Full-suite runs: 0. New dependencies: 0.
Unnecessary dataset regeneration: avoided. Necessary fixture-image rendering
preserves lineage rather than inventing additional purchases or receipt fields.

This demo does not resolve published-storage durability and is not release
authorization. No public publishing or main merge was initiated.
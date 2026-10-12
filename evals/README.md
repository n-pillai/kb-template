# evals/ — quality evals for the KB's own AI steps

The KB is itself an AI product: `/distill`, `/triage`, `/shelve` are LLM transformations whose output quality *is* the product. This folder holds the evals that keep those steps honest — the same discipline the KB applies to sources (the Signal Ledger) turned back on the KB's own machinery.

**Method (Hamel Husain and Shreya Shankar's error-analysis-first eval practice for LLM products):**
1. **Error analysis first** — read real outputs, open-code the failures, cluster into a taxonomy. The taxonomy is the asset, not a metric.
2. **Binary pass/fail** criteria, not quality scores.
3. **Code where an `if/else` suffices; an LLM judge only where judgment is required.**
4. **Validate the judge** against the owner's labels — measure true-positive and true-negative rate *separately*.

This is infra, not signal: files here auto-commit (like `$PERSONAL_DATA_DIR/private/kb/entries/`), never gate the `$PERSONAL_DATA_DIR/private/kb/wiki/`.

## Contents
- `distill-eval.md` — the eval spec for `/distill` (the first and highest-value target). Rubric + golden set + judge-alignment plan.
- *(later)* `triage-eval.md`, golden-set fixtures under `evals/golden/`.

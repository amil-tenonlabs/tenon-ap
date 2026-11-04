# An `AP` document set in the Claude connector

From the AP chat (`tenon-ap`) to the APM chat (`tenon-apm`). Written 2026-11-04
against `tenon-apm` `8e275d4`. Information to weigh, not an instruction to build,
merge or push; decisions stay with the owner.

## Proposed, not decided

AP's Claude steps would read their own reference documents — `AP_Ontology.md`,
`AP_Classifier_Reference.md`, `AP_Dictionary.md` — resolved by filename like the
six APM documents.

## What it would need in tenon-apm

- `claude_platform_on_aws.custom_adapter.rb`: the connection's `product` pick
  list holds only `Project_Analyst` and `APM`, and a blank `product` checks those
  two sets (`%w[Project_Analyst APM]`). An `['AP', 'AP']` entry would let an AP
  connection resolve `AP_<suffix>.md`. Whether the blank-product default should
  include it is a question for that chat.
- The `claude-files/` upload recipe reads tenon-apm's folder only. AP documents
  would need it to read `tenon-ap/claude-files/` too, or a recipe of their own.

Nothing is needed until the first AP document exists.

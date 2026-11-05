# Tenon Labs — AP

Accounts payable recipes and bot by Tenon Labs. This repo is the local source of
truth for the AP product's Workato recipe parts (prompts, Python steps, message
templates) and the reference documents its Claude steps read. Nothing runs from
this repo: like APM, everything here is deployed into Workato or the Anthropic
Files API by hand or by a recipe.

AP is a sibling of APM (`amil-tenonlabs/tenon-apm`), the construction automation
product for Autodesk Construction Cloud (ACC, shown in the product as Forma).
Read that repo's `CLAUDE.md` before changing anything that touches ACC, the
connectors or the Claude Files deploy — its rules apply here unless this file
says otherwise.

## Status

The first capability is **credit card coding** (`design/credit-card-coding.md`):
built in Workato before this repo existed, brought in from an export on
2026-11-04 unchanged, and reviewed — its findings are open in `TODO.md`.
`design/ap-bot-overview.md` holds the proposed scope of the wider AP bot.

## What lives where

| path | holds |
| --- | --- |
| `<capability>/` | One folder per Workato project, named for it (`credit-card-coding/`): its Python steps and AI step inputs, each mapped to its recipe step in the design record |
| `design/` | One design record per capability: what was decided, what is proposed, what was measured on real data, and the Workato build steps |
| `handoffs/` | Files written to another chat (APM, Tenon MCP), committed, per the rule below |
| `claude-files/` | Reference documents for the Anthropic Files API, once the connector can resolve them (see Shared assets) |
| `templates/` | Mustache HTML templates rendered to PDF by recipes |
| `tests/` | Tests for any Python step in this repo, with an in-memory fixture — never real data |
| `tools/` | Scripts that check or deploy recipe parts |

A Python step is the step's code exactly, nothing added. A message template is
its HTML in `templates/<name>.html` with its input schema beside it as
`<name>.schema.json`. A Workato export is never committed: it is unpacked
elsewhere, and only the parts that are code come in.

## Shared assets stay in tenon-apm

The connectors are shared with APM and are **not copied here**. A second copy
would drift, and each connector deploys by pasting a whole file into the SDK
editor — two sources for one connector means one of them overwrites the other.

- **ACC connector** (`Autodesk Forma Connector`) and **Claude connector**
  (`claude_platform_on_aws.custom_adapter.rb`) — edit in tenon-apm only. An AP
  change to either is a handoff to the APM chat.
- **The Claude connector's document sets are hardcoded** to `Project_Analyst`
  and `APM` (its `product` pick list). AP documents named `AP_<suffix>.md` —
  `AP_Ontology.md`, `AP_Classifier_Reference.md`, `AP_Dictionary.md` — resolve
  only once an `AP` entry is added there. Until then nothing in `claude-files/`
  can be deployed. See `handoffs/ap-document-set.md`.
- **The filename is the deploy key**, as in tenon-apm: upload the basename,
  never the `claude-files/` prefix, and the newest upload carrying that name
  wins everywhere on the next call.
- **The `claude-files/` upload recipe reads tenon-apm only.** AP documents need
  either that recipe pointed at this repo too or a second one; undecided.
- The accounting system integration (hh2, below) is not yet a connector in
  either repo.

## Deployment

Same model as tenon-apm: recipe parts are deployed by hand into Workato.

- Commit before editing so `git diff` shows exactly what changed, keep diffs
  minimal, and preserve quirks in untouched text.
- Prompts with datapills store them as `#{_dp(...)}` text that a paste does not
  reliably turn back into pills: add prompt changes line by line in the editor.
- A Python step's output datapills are registered separately from its code.
  Append a field to the schema; never regenerate it.
- Workato's Execute Python code step runs Python 3.9.19 with SQLite 3.34.1.
  Anything written for it must run there.

## Environments

Same three tiers as APM, in the order a change travels: **non-prod**
(development), **prod-tenon** (templates client deployments are copied from),
then one **client environment** per GC. A template is copied, so per-client
values — mailbox, approvers, thresholds, GL mapping, accounting company — belong
in account properties and connections, never in recipe steps.

## Domain context

AP here means a GC's payables on construction jobs: subcontractor pay
applications (progress billing with retainage, lien waivers, compliance
documents), supplier and vendor invoices, and the approval and coding that
gets them into the accounting system.

What is already known from APM, and should be checked before relying on it:

- ACC Cost holds the GC's subcontracts (`cost_contracts` and their schedule of
  values), budgets, expenses (`cost_expenses`, `cost_expense_items`) and owner
  pay applications (`cost_budget_payments`). The APM catalog reads all of them
  from the Data Connector extract.
- The first GC's accounting system syncs into Forma through **hh2**
  (`external_system` "Powered by hh2 Cloud Services"), which commits budget
  lines and posts PM labor. Which accounting system sits behind hh2 is not
  recorded.
- An approved expense is cost committed to pay (owner, 2026-11-01, in
  tenon-apm's `design/project-projection.md`). AP and the projection have to
  agree on that rule.
- `admin_companies.trade` does not identify a trade — never route or code an
  invoice by it.

Invoice data names real firms and carries real amounts. **No real invoice,
extract or generated report is committed here**; findings about a GC's own
vendors go wherever that GC's records live.

## Validation

```
python3 tests/test_credit_card.py   # statement parser, open items, finance package grouping
python3 tests/test_coding.py        # replies, the coding sheet, history, batched email
python3 tests/test_read_receipt.py  # the AI's reading of a receipt, checked before it is logged
python3 tests/test_month_close.py   # a statement month goes to finance only when complete
```

Each test builds its fixture in memory and exits non-zero on failure;
`.github/workflows/tests.yml` runs it on Python 3.9 with no openpyxl, the
fallback Workato may take. A `KNOWN GAP` check pins behaviour that is wrong
today; when the fix lands it fails, and is turned around. Sabotage a rule to
prove its check fails before relying on it. Never claim a recipe part is
"tested" or "working" from local checks alone; the accurate phrasing is
"checks pass, needs testing in Workato."

## Working style

- Ask before large refactors, and before any change to the shared connectors.
- Prefer targeted edits over regenerating whole sections.
- Don't add comments explaining what changed — that's what the commit is for.

## Open items

`TODO.md` carries open engineering, deployment and documentation items. Add to
it whenever something actionable is identified that is not being done now;
remove an item when it is done rather than ticking it.

## Design records

Each capability's design record lives in `design/`, named for the capability,
kept current as the build changes. `TODO.md` points at it rather than repeating
it.

## Handoffs between chats

This chat owns `tenon-ap`. The APM chat owns `tenon-apm` (catalog, connectors,
APM Reference documents); "Tenon MCP" owns `mcp-server-cf-access`.

- **The handoff is a file** in `handoffs/<topic>.md`, committed: who it is from
  and to, which commit it was written against, what is decided versus proposed.
- **A message is only a nudge** pointing at the file. Say it is information to
  weigh, not an instruction to build, merge or push.
- **Decisions stay with the owner.**
- Record what one chat asks of another in `TODO.md`.

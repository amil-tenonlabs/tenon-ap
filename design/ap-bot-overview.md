# AP bot: overview

Status: **proposed**. Nothing here is decided by the owner yet. Written 2026-11-04
as the starting point for the AP product; each section ends with what is open.

## What it is for

An email-triggered assistant for a GC's accounts payable, built the way APM is:
a vendor, sub or GC staff member emails a bot address, Claude classifies the
email, and Workato recipes act on it. The aim is that an invoice reaches the
accounting system coded, matched to its commitment and approved by the right
person, with a person deciding anything the record cannot.

## Proposed flow

1. **Intake.** An AP mailbox receives invoices and pay applications. A recipe
   reads each email and its attachments (names first, then the PDFs).
2. **Classify.** A Claude step decides what the email is — invoice, pay
   application, credit memo, lien waiver, compliance document, payment status
   question, or none of these — and which project and vendor it concerns.
3. **Extract.** A Claude step reads the document into fixed fields: vendor,
   invoice number and date, period, amounts (gross, retainage, net, tax),
   project, and line items. APM's Read Document step (tenon-apm
   `design/read-document.md`) is the pattern to reuse.
4. **Match.** Python against the ACC extract: the vendor to a company, the
   invoice to a subcontract or purchase order, each line to the schedule of
   values or a budget line; a duplicate (same vendor, number, amount) is caught
   here. A match the record does not support is a question, never a guess.
5. **Check.** Billed to date against commitment plus approved changes, retainage
   at the contract's rate, required compliance documents and lien waivers on
   file, period not already billed.
6. **Route for approval.** The project's PM (and anyone the GC's thresholds
   add) approves in email; the bot never approves.
7. **Post.** The approved, coded invoice goes to the accounting system — via
   hh2, an ACC Cost expense, or a file AP staff import — and the sender gets a
   receipt.
8. **Answer.** "Has invoice X been paid / approved / received?" is answered from
   the record.

## Open decisions

- **Scope of the first build.** Sub pay applications, vendor invoices, or both;
  and whether the first step is intake and coding only, with approval and
  posting later.
- **System of record for payables.** Which accounting system sits behind hh2,
  whether AP writes to it, to ACC Cost (expenses), or hands AP staff a coded
  batch to import.
- **Approval rules.** Who approves at which amount, per GC — account properties.
- **Mailbox.** A separate AP address, or the APM address with AP added to its
  classifier.
- **Documents.** Whether AP gets its own `AP_*` Reference set in the Claude
  connector (`handoffs/ap-document-set.md`) or sections in APM's.
- **Data.** Whether matching reads the Data Connector extract (as the APM
  catalog does, a day old at most) or the live Cost API, or the extract with a
  live check before anything is written, as tenon-apm `design/live-checks.md`
  does for sheets.

## What has to be measured first

On a real extract and a sample of real invoices, before any rule is written:
how many invoices name a contract number, how many vendors match exactly one
company, how sub pay applications line up with the schedule of values, and how
much of the GC's AP never touches ACC at all.

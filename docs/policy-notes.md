# Policy notes (starter)

These notes are a starting point for an AI use policy for this assistant. They are mapped to the four functions of the NIST AI Risk Management Framework (AI RMF 1.0): Govern, Map, Measure, Manage. They are not legal advice and not LCRA policy.

## Govern
- Name a business owner for the assistant and an owner for each data source (`data/governance.yaml`). The governance page shows anything still unassigned.
- Admin actions (re-ingest, refresh, run evals) are limited to `ADMIN_USERS`.
- Keys live in `.env`, never in git.

## Map
- Use case: retrieve and cite public flood, water supply and CIP summary content. Out of scope: release decisions, flood warnings, contract interpretation, legal advice.
- Data: every document carries a label (public, field-tech, cip-restricted). Unlabeled files default to cip-restricted.
- Where data goes: with `LLM_PROVIDER=openai` and the default endpoint, retrieved text is sent to a hosted API. With `ollama`, nothing leaves the network. The governance page states which is active.

## Measure
- Golden-set evals run in CI on every push, and on demand against the live model from the dashboard.
- The dashboard tracks usage, cost, latency, unanswered rate and user feedback.
- RBAC leak tests must stay at zero leaks.

## Manage
- The gap report drives which documents are added next.
- The nightly refresh re-checks public sources and records every change in a changelog.
- If evals drop below threshold, CI fails and the change does not ship.
- Every answer carries citations, so a person can check the source before acting.

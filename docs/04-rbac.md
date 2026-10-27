# 4. Access control

The rule: **a chunk the user may not read must never enter the prompt.** Once text is in the model's context, you cannot reliably stop it from appearing in the answer. Prompt instructions like "don't reveal secrets" are not a control.

## How it works here

- Each document has one label: `public`, `field-tech`, or `cip-restricted`.
- Each role maps to a set of labels (`app/rbac.py`).
- The search query includes `WHERE label IN (...)` (SQLite) or `label = ANY(...)` (pgvector). Restricted rows are never loaded, so they can't win the ranking.
- `rag.py` re-checks every hit. Defense in depth costs one line.
- Unknown users get `public`.

## The tests

`tests/test_rbac.py` asks probing questions as `guest`, `maria`, and an unknown user, and asserts that no restricted source is returned and no secret term appears in the answer. Then it confirms `dev` can see the content, so we know the test isn't passing because the doc is missing.

## Production notes

- Replace the `X-User` header with SSO (OIDC/SAML) and map directory groups to roles.
- Labels should come from your document management system, not hand-edited files.
- Log every access to restricted content. CIP-004 and CIP-011 auditors will ask.

## Exercise

Add a role `vegetation-contractor` that can see only `public` and a new label `vegetation`. Write the leak test first, watch it fail, then make it pass.

# 10. Measure and govern

Chapters 1 to 9 built an assistant that answers with citations and keeps restricted content out of the wrong hands. This chapter answers the next question a director asks: "How do we know it's working, and who's in charge of it?"

AI is a force multiplier, not magic. A multiplier needs a baseline. If you can't say how many questions it handled, what they cost, how often it said "I don't know", and whether people found the answers useful, you can't defend the budget or improve the system. So this chapter adds measurement first, then governance on top of it.

## Part 1: Measure

### What we track and why

| Signal | Where it comes from | What it tells a director |
|---|---|---|
| Questions per day | `query_log` | Adoption. Is anyone using it? |
| Cost per day and per question | token counts × `PRICE_*_PER_M` | Is it cheap compared to staff time? |
| Average latency | timer around each request | Will people wait for it? |
| Unanswered rate | `outcomes` table | Coverage. What share of questions do our documents not cover? |
| Thumbs up / down and comments | `feedback` table | Do people trust the answers? |
| Eval scores over time | `eval_runs` table | Quality. Did a model or document change make it worse? |

Open `http://localhost:8000/dashboard` to see all of them on one page. The charts are plain inline SVG drawn by about 20 lines of JavaScript. There's no build step and no CDN, so the page also works on an on-prem network with no internet access.

### How "unanswered" is decided

`app/measure.py` marks an answer as unanswered when either of these is true:

1. The model said so ("I don't know", "not in the context", and similar phrases).
2. The best retrieved chunk was a weak match: cosine similarity below `LOW_CONFIDENCE_SCORE` (default `0.15`).

Rule 2 catches the case where the model answers anyway from a poor match. The right threshold depends on your embedding model. Start with the default, read the gap report for a week, and adjust.

**Exercise:** ask five questions you know aren't covered (parks hours, a transmission line route, next year's budget). Check that each one shows up in the gap report. If one doesn't, look at its `top_score` and decide whether the threshold should move.

### The gap report

Every unanswered question, and every answer that got a thumbs down, is grouped by topic. The topics are a short keyword list in `measure.TOPICS`, and each topic carries a list of documents that would close the gap. For example, drought questions suggest adding the Drought Contingency Plan PDF.

We used keyword groups instead of embedding clusters on purpose. In a meeting, "these 14 questions mention curtailment or restrictions" is easy to check and easy to argue with. If your volume grows to thousands of questions a week, cluster the question embeddings instead. The data is already in the `outcomes` table.

This turns the assistant into a continuous-improvement loop:

1. People ask questions.
2. The gap report shows what the documents don't cover.
3. A content owner adds those documents.
4. The unanswered rate goes down, and you can show it.

### Feedback

Each answer in the chat page has 👍 / 👎 buttons and an optional comment. They post to `/feedback` with the answer's `qid`, a random id returned by `/ask`. Feedback joins to the original question, so a thumbs down lands in the gap report even if the model did produce an answer.

### Eval history

Chapter 6 ran the golden set in CI. Now each run is also stored in `eval_runs`, so the dashboard can show quality next to usage. Two details matter:

- Eval questions call `rag.ask(..., log=False)`. Test traffic never inflates the usage numbers.
- CI scores the offline `fake` provider. To score the real model you'll demo with, click **Run evals now** on the dashboard as an admin user (`tim` or `dev`). It calls `POST /admin/run-evals`. With a paid API that's about 21 short calls, a few cents.

### Admin endpoints

Everything under `/admin/` now checks that the caller is in `ADMIN_USERS` (default `dev,tim`). That includes the existing `/admin/reingest`, which was open before. The user still comes from the demo `X-User` header. In production that would come from your identity provider, and the check would stay the same.

**Exercise:** call `curl -X POST -H "X-User: guest" localhost:8000/admin/reingest`. You should get a 403.

## Part 2: Show the access control, then govern the data

### Side-by-side access view

Chapter 4 proved with tests that restricted chunks never reach the wrong user. Tests convince engineers. Directors need to see it. Open `http://localhost:8000/compare`, pick two users, and ask one question. Each column runs a normal `/ask` as that user, with that user's role, so the view can't leak anything the chat page wouldn't. Sources that only one user could retrieve are highlighted in red.

Good pairs to try:

- **guest vs tim:** "What firewall protects the Electronic Security Perimeter at the control center?" Tim's column cites the (fictional) CIP-restricted note. Guest's column never sees it.
- **guest vs maria:** "What must a technician get from the control center before touching equipment after a feeder trip?" Maria's field-tech procedure appears only for her.

That's the five-second version of "our sensitive data stays protected."

**Exercise:** add a fifth demo user in `app/rbac.py` with a new role that can read `public` and `cip-restricted` but not `field-tech`. Compare that user against maria.

### Governance page

Open `http://localhost:8000/governance`. It answers the questions any AI review board asks:

- **Which sources?** Every document in the index, with its link and chunk count.
- **How sensitive?** The label on each one.
- **Who owns it?** From `data/governance.yaml`. Anything not assigned shows `unassigned` in red. An owner is the person who keeps a source accurate and decides whether it belongs in the assistant at all.
- **How fresh?** The date it was retrieved, plus the last time the nightly refresh checked it and when it last changed (Part 3).
- **Which model sees it?** Provider, chat model, embedding model, endpoint, and a plain yes or no on whether data leaves the network. With the default OpenAI endpoint the answer is yes. With Ollama it's no. Say that out loud in a utility meeting before someone asks.

Owners resolve from most specific to least specific: an exact file name, then a file name prefix, then the label, then `unassigned`:

```yaml
owners: {lcra-drought.md: Water Resources}
owner_prefixes: {lcra-: Public Information}
label_owners: {cip-restricted: CIP Senior Manager}
```

The page links to [policy notes](policy-notes.md), a starter policy organized by the NIST AI RMF functions (Govern, Map, Measure, Manage). The JSON at `/api/governance` is the seed of a separate governance repo with a model and use-case registry, a risk assessment template and a full RMF mapping. Keep the data here, and keep the policy work there.

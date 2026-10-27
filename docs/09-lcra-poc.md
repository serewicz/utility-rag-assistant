# 9. LCRA proof of concept: Highland Lakes flood and water supply assistant

Chapters 1 to 8 used NERC CIP summaries and sample procedures. This chapter swaps in real public documents from the Lower Colorado River Authority (LCRA) and adds one live data feed. The goal is a proof of concept a utility could look at and say, "we would use that."

## The business problem

LCRA manages six Highland Lakes dams, the lower Colorado River's water supply, and a large transmission system. Every rain event and every drought month brings the same questions, from staff, from firm water customers, from lakefront residents, from reporters and from elected officials:

- "Is Lake Travis going to open floodgates? At what level?"
- "What do the downstream gauges at Austin, Bastrop and Columbus have to do with it?"
- "What triggers mandatory curtailment for my city?"
- "What is the firm water rate next year?"
- "How do I get flood operations alerts?"

The answers already exist, spread across dozens of lcra.org pages, PDFs, and the Hydromet gauge network. Staff in public information, customer service, water contracts and river operations answer them by hand, and they answer them fastest exactly when they are busiest: during a flood or a drought.

An assistant that finds the right paragraph, quotes it with a link, and adds the current lake level frees those people for the work only they can do. That is the force-multiplier framing. It does not make release decisions, issue warnings or interpret contracts. It retrieves and cites.

## Why this data (and not transmission or outages)

We looked at three candidate areas:

| Area | Public documents | Daily questions | Live data | Verdict |
|---|---|---|---|---|
| Flood operations and lake levels | Rich: dam-by-dam pages, Mansfield Dam release rules, FONS | Yes, and spikes during floods | Yes, Hydromet | **Chosen** |
| Water supply and drought (WMP, curtailment, firm water) | Rich: WMP, curtailment rules, rates, restrictions | Yes, from customers and cities | Combined storage is reported | **Chosen (same corpus)** |
| Transmission and outages | Project and routing pages, little operational detail | Few public questions | No public feed | Not chosen. Operational detail is CIP-protected, as it should be |

Flood and water supply share the same lakes, the same storage numbers and the same audience, so they make one coherent corpus. Transmission stays in the earlier CIP chapters, where the point is access control.

## The documents

18 public pages from lcra.org, retrieved 2026-10-26. All are labeled `public`, so every demo user can see them.

| File | Title | Source |
|---|---|---|
| `lcra-agricultural-irrigation-use.md` | Agricultural Irrigation Use (LCRA) | https://www.lcra.org/water/permits-contracts/water-supply-contracts/agricultural-irrigation-use/ |
| `lcra-dams-and-lakes.md` | Dams and Lakes (LCRA) | https://www.lcra.org/water/dams-and-lakes/ |
| `lcra-drought.md` | Every drop counts (LCRA) | https://www.lcra.org/water/drought/ |
| `lcra-firm-water-use.md` | Firm Water Use (LCRA) | https://www.lcra.org/water/permits-contracts/water-supply-contracts/firm-water-use/ |
| `lcra-flood-management.md` | Managing Floods in Flash Flood Alley (LCRA) | https://www.lcra.org/water/flood-management/ |
| `lcra-flood.md` | Get to know the Highland Lakes (LCRA) | https://www.lcra.org/water/flood/ |
| `lcra-floodgate-operations-notification-system.md` | Flood Operations Notification Service (LCRA) | https://www.lcra.org/water/flood-management/floodgate-operations-notification-system/ |
| `lcra-highland-lakes-overview.md` | The Highland Lakes and Colorado River (LCRA) | https://www.lcra.org/water/highland-lakes-overview/ |
| `lcra-key-elevations-for-lake-travis-during-floods.md` | Mansfield Dam Flood Operations (LCRA) | https://www.lcra.org/water/flood-management/key-elevations-for-lake-travis-during-floods/ |
| `lcra-lake-lowerings.md` | Lake Lowerings (LCRA) | https://www.lcra.org/water/quality/lake-lowerings/ |
| `lcra-mandatory-water-use-curtailment.md` | Mandatory Water Use Curtailment (LCRA) | https://www.lcra.org/water/permits-contracts/water-supply-contracts/mandatory-water-use-curtailment/ |
| `lcra-updating-the-water-management-plan.md` | Updating the Water Management Plan (LCRA) | https://www.lcra.org/water/water-supply-planning/water-management-plan-for-lower-colorado-river-basin/updating-the-water-management-plan/ |
| `lcra-water-management-plan-for-lower-colorado-river-basin.md` | Water Management Plan for the Highland Lakes (LCRA) | https://www.lcra.org/water/water-supply-planning/water-management-plan-for-lower-colorado-river-basin/ |
| `lcra-water-supply-operations.md` | Water Supply Operations (LCRA) | https://www.lcra.org/water/water-supply-planning/water-supply-operations/ |
| `lcra-water-supply-planning.md` | Water Supply Operations and Planning (LCRA) | https://www.lcra.org/water/water-supply-planning/ |
| `lcra-water-use-restrictions.md` | Water Use Restrictions (LCRA) | https://www.lcra.org/water/permits-contracts/water-supply-contracts/water-use-restrictions/ |
| `lcra-water-use-summary.md` | Water Use Summary (LCRA) | https://www.lcra.org/water/water-supply-planning/water-use-summary/ |
| `lcra-wirtz-dam-project.md` | Wirtz Dam Floodgate Replacement Project (LCRA) | https://www.lcra.org/water/dams-and-lakes/wirtz-dam-project/ |

They live in `data/docs/lcra/`. Ingestion reads subfolders, so nothing else had to change.

### How they were ingested

1. Checked `https://www.lcra.org/robots.txt`. It only blocks `/wp-admin/`. We fetched 18 pages, one per second, with an identifying User-Agent.
2. Took the URL list from LCRA's own `page-sitemap1.xml`, filtered to flood, dams, drought and water supply pages.
3. Converted each page's `<main>` element to Markdown with BeautifulSoup and markdownify, dropping navigation, scripts and forms.
4. Added front matter: `title`, `label: public`, `source_url` (the exact page), and `retrieved` (the date). The date matters: rates, drought stage and storage numbers change.
5. At ingest time, `app/ingest.py` now strips Markdown link targets (`[text](url)` becomes `text`). URLs waste tokens and pull retrieval toward the wrong chunks.

Two things to notice, because they will happen at any utility:

- **Pages go stale.** The curtailment page says LCRA "is currently in Stage 2" and projects possible DWDR conditions "during the first half of 2026." The assistant will repeat that faithfully. A production system needs a refresh schedule and a data owner (see below).
- **Some numbers are drawn by JavaScript.** The drought page reads "The lakes are about  full." with the percentage missing, because the page fills it in from a script. Scraping HTML does not get it. That is one reason for the live data tool.

The PDFs linked from these pages (Water Control Manual, Drought Contingency Plan, pro rata rules) sit behind a download page, not a direct file link. They are the obvious next documents to add, by hand, with an entry in `data/docs/labels.yaml`:

```yaml
lcra-firm-drought-contingency-plan.pdf: public
```

## Live data: Hydromet lake levels

`app/hydromet.py` is a small tool. If a question asks for a *current* level ("now", "today", "current", "latest") and names a lake, it fetches the current reading from LCRA Hydromet and puts it first in the context, ahead of the retrieved documents. The model can then answer "Lake Travis is at 677.2 ft msl now; floodgate releases can begin above 681 ft msl" with both sources cited.

- Source page: https://hydromet.lcra.org/Reports/LakeLevel
- Data: `https://hydromet.lcra.org/api/GetLakeLevelsForAllSites`, the JSON the public page itself loads. It is **not a documented or supported API**. Treat it as best-effort. In production, ask LCRA's Hydromet team for the supported feed.
- On/off: `HYDROMET_LIVE=1` (on in `docker-compose.yml` and `.env.example`, off by default in code and in CI).
- Failure mode: a 5-second timeout, no retries. If it fails, the assistant answers from documents only.
- Tests: `tests/test_hydromet.py` mocks the feed. CI never touches the network.

This is the pattern behind "tools" and MCP servers: retrieval answers "what are the rules", the tool answers "what is happening now", and the model combines them.

## Evals

`evals/golden.yaml` has 13 new questions grounded in these pages, each with the document that must be retrieved and words the answer must contain. Every expected answer was checked against the page text.

With the offline `fake` provider: **retrieval 100% (21/21), answer accuracy 95% (20/21)**.

The one miss is instructive: "What are the control stage and control flow at Bastrop?" The answer (27.2 ft, 45,000 cfs) is in a table. The fake provider picks a single sentence and retrieves the right chunk, but picks the wrong line. A real model reads the table. We kept the question in the set rather than rewording it until it passed, because a golden set that only contains easy questions measures nothing.

Two changes came out of adding the new corpus, and both are typical:

- The original CIP question "How quickly must access be removed after a termination?" stopped retrieving its document once 18 new pages were added. The fake embedder hashes words into 256 slots, and more text meant more collisions. Raising it to 1024 fixed it. Your evals are what told you; nobody would have noticed by hand.
- The fake answer picker now weights rare question words higher (a tiny IDF), so "Bastrop" counts more than "Mansfield" when every sentence mentions Mansfield.

## Try it

Pick **guest** in the dropdown. These are public documents, so the lowest-privilege user is the right demo. Then pick **maria** or **tim** and notice the answers are the same: access control only changes what restricted content you can see.

- At what Lake Travis elevation can LCRA begin floodgate releases from Mansfield Dam?
- What is the current level of Lake Travis? (live, needs `HYDROMET_LIVE=1`)
- What is the initial minimum curtailment percentage in the Drought Contingency Plan?
- Is FONS a flood warning service?
- What is the firm water rate per acre-foot starting with the January 2027 billing cycle?
- How many floodgates does Wirtz Dam have and what is their discharge capacity?

With the `fake` provider you get the single best-matching sentence. Set `LLM_PROVIDER=openai` (with a key) or `ollama` for full answers.

## What a production rollout at a utility would need

**Identity and access.** Replace the `X-User` header with SSO (Entra ID or Okta via OIDC). Map directory groups to roles in `app/rbac.py`. Public content stays public; internal flood procedures, gate operating orders and contract files get their own labels and owners.

**Data owners.** Every document set has a named owner: River Operations for flood content, Water Contracts for rates and curtailment, Public Information for public pages. The owner approves what goes in, its label, and when it is retired.

**Refresh schedule.** Public pages: nightly re-crawl from the sitemap, with a diff report to the owner. Rates and drought stage: re-ingest when the Board acts. Live data: the supported Hydromet feed, cached for a minute. Every answer shows the `retrieved` date so users can see how fresh it is.

**On-prem models.** Run the model with Ollama or vLLM inside the utility's network (`LLM_PROVIDER=ollama`, chapter 7). Public data does not require it, but internal documents will, and it is simpler to run one architecture.

**NERC CIP.** Keep the assistant out of the Electronic Security Perimeter. It should never connect to SCADA, EMS or gate controls, and it should read Hydromet the way the public does, not from operational systems. If BES Cyber System Information is ever ingested, the server, logs and backups fall under CIP-011 information protection, access to it under CIP-004, and the label filter in this repo is one control, not the whole program.

**Guardrails for flood season.** The assistant must point to official channels for warnings (NWS, local emergency management, FONS) and never predict releases. The system prompt already says "Never guess about safety or compliance steps"; add a fixed disclaimer to any answer that touches flood operations, and an eval question that checks it.

**Measure it.** Track questions per day, deflected calls, time to answer, and thumbs up/down by topic in `query_log`. A 90-day pilot with Public Information and Water Contracts staff is enough to decide whether to scale.

## Exercise

1. Download the Firm Customer Drought Contingency Plan PDF from the firm water page, put it in `data/docs/lcra/`, label it in `labels.yaml`, and add two golden questions about it.
2. Add `"current"`-style support for river flows using Hydromet's River Stage and Flow report (https://hydromet.lcra.org/Reports/RiverStageFlow). Mock it in a test first.
3. Write an eval question for the flood disclaimer guardrail, watch it fail, then make it pass.

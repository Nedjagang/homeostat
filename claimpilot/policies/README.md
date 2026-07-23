# Policy corpus (RAG source)

20 synthetic clause-level policy documents across two policies: `HP-100-*.md` (homeowner,
10 docs) and `AU-220-*.md` (auto, 10 docs). Each doc is a single retrievable clause — this
is what `retriever.py` chunks and ranks over.

The sample claims in `../claims/claims.example.json` split cleanly against this corpus:
- 7 are answerable (each maps to exactly one clause doc above).
- 3 (`CLM-101/102/103`) are deliberately **unanswerable** — no clause here mentions a
  neighbor's separate policy, meteor strikes, or an unfiled claim's payout. A grounded
  agent must abstain; the overconfident chaos prompt answers anyway and Tier 0 (and later
  the judge) flags it.

Synthetic data only. No real customer or policy data.

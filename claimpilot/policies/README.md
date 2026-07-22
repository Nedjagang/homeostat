# Policy corpus (RAG source)

Put ~20 short **synthetic** policy documents here (`*.md` / `*.txt`), e.g. `HP-100.md`,
`AU-220.md`. These are the retrieval corpus ClaimPilot grounds its answers in.

Design them so the sample claims in `../claims/claims.example.json` split cleanly:
- ~7 are answerable from these docs.
- 3 are deliberately **unanswerable** (no supporting clause exists) — a grounded agent
  abstains; the overconfident chaos prompt answers anyway and the judge scores it low.

Synthetic data only. No real customer or policy data.

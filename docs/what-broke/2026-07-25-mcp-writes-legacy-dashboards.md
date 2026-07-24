# What broke: the official MCP writes dashboards the new UI calls legacy

**Symptom.** Both ClaimPilot dashboards, created through the official SigNoz MCP server's
`signoz_create_dashboard` (after dutifully dry-running every query shape), rendered —
but showed up in the **legacy** dashboards view. The redesigned "Dashboards V2"
experience wants `schemaVersion: v6`, a strictly-enforced Perses-based schema; the V2
API refused ours outright: `501 — dashboard is not in v6 schema`.

**Root cause.** SigNoz is mid-transition (upstream migration scheduled the week of
July 27). The UI already writes v6; the MCP server (v0.9.0) still writes the classic
`widgets`/`layout` model. Two official tools, two schemas, one week apart.

**Fix.**
1. Rebuilt both dashboards natively via `POST /api/v2/dashboards` with hand-authored v6
   bodies (Perses `spec.panels` + `layouts` with `$ref`s; the inner query specs are the
   same v5 builder shapes the alerts use — those did not change).
2. There is **no in-place conversion**: `PUT /api/v2/dashboards/{id}` on a legacy
   dashboard also 501s. New UUIDs, delete the legacy pair.
3. The committed pack (`signoz/dashboards/*.json`) is now v6, and `signoz/push-packs.py`
   creates-or-updates dashboards by Perses `name` through the V2 API — the UI's
   Import-JSON dialog predates v6, so the script is the import path.

**Lessons:**
- On a fast-moving platform, "created successfully" is not the finish line — check
  *which generation* of the thing you created. The error surface (`501 unsupported`,
  not `400 invalid`) was the tell that we were behind the schema, not wrong in it.
- Validation-by-API beats validation-by-docs: the v6 validator's error messages
  (`schemaVersion must be "v6"`, `name is required`) converged us to a correct payload
  in three attempts.
- When two official tools disagree, prefer the one the platform is migrating *toward* —
  and file the gap as feedback (the MCP server lagging the V2 schema is exactly the kind
  of thing a hackathon should surface to the SigNoz team).

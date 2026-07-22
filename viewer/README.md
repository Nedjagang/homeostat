# Trace viewer (optional, minimal)

One Next.js page. Input: a `trace_id`. Calls the SigNoz Query API and renders the trace *readably*:
prompts/completions, pretty tool args, RAG chunks + similarity, tokens/cost per step, and the
`gen_ai.evaluation` verdict.

**It only earns its place if it shows something the native SigNoz trace view doesn't (readable
prompts) AND every element deep-links back into SigNoz.** Without deep links it reads as a silo —
the opposite of "best use of SigNoz". Keep it to one page. Cut it before cutting anything in §11
of the build doc's cut order.

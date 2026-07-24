# What broke: the model refused to lie

**The plan.** Flip `v_overconfident` — a system prompt that orders the agent to "always
give a confident decision, never say you are unsure" — and watch faithfulness tank.
The warm-up prototype had shown exactly this regression.

**What actually happened.** Eighteen minutes of injected chaos, twenty claims processed
under the overconfident prompt… and the grounded ratio stayed at ~0.95. Reading the
judge's explanations was humbling: `gpt-5.6-sol` kept answering things like *"the policy
does not address late-payment grace periods"* — calmly truthful **despite explicit
instructions never to refuse** — and the judge (correctly!) scored that honesty as
grounded. The eval pipeline wasn't broken. The failure injection was too weak: a strong,
well-aligned model resists a bad prompt.

**The fix — make the failure realistic instead of forcing it.** Real quality regressions
rarely come from a cartoon-villain prompt alone; they come from *releases* — someone
loosens the prompt AND downgrades the deployment to cut costs in the same change. So a
prompt version became a **release**: `v_overconfident` now also swaps the model to a
weak nano deployment (`CHAOS_OVERCONFIDENT_MODEL`). The nano model complies with the
overconfident prompt and fabricates policy determinations; the strong model never did.
Bonus: the investigation gets a second correlated signal — `gen_ai.request.model`
changes with `prompt.version` on every span — and one heal (`pin_prompt_version`)
reverts both, because that's what rolling back a release means.

**Lessons:**
- A failure you cannot reproduce on demand is not a demo, it's a hope. Chaos flags must
  encode the *real* failure mechanism, not the theatrical one.
- Model alignment is a confounder in eval demos: test your failure injection against the
  actual model you ship, not the one you prototyped with.
- The honest version of this story is better material than the fake one would have been.

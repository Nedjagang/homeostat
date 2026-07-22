"""Replay claims at volume to prove the data-plane contract holds at scale:
metric cardinality stays bounded and disk growth is linear/controlled.

Capture before/after numbers (series count, disk) for the blog's scale section.
"""
# TODO: loop over synthetic claims at a target rate; optionally fan out concurrency.
# Assert (or just record) that the number of gen_ai.evaluation.score series stays bounded
# regardless of how many claims are processed (that's the cardinality-discipline proof).

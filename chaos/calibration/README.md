# Judge calibration

The judge is a **signal, not ground truth** — prove you know that.

- Hand-label ~30–50 answers as supported / unsupported (`labels.example.json`).
- Run the judge on the same set; compute agreement (accuracy / precision / recall vs your labels).
- Write `report.md`: the agreement %, a few examples where the judge was wrong, and the takeaway
  (we alert on *drift vs baseline*, so mild miscalibration matters less).

Cite these numbers in the blog. Keep scratch work in `scratch/` (git-ignored); commit the final report.

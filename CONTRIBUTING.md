# Contributing

Contributions should improve traceability, generalization, or review safety.

1. Add a failing public or synthetic evaluation case before changing extraction logic.
2. Make the smallest general rule that fixes the case; do not add company-name branches.
3. Run `ruff check .`, `pytest`, and both public-company evaluations. A rule that fixes one case but breaks the other is not accepted.
4. If a public filing is required, commit its URL, checksum, ground truth, and download instructions - not the filing itself.
5. Keep human ratings out of generated audits.
6. Explain accounting boundaries and false-positive risks in the pull request.

Never contribute private CRM data, personal contacts, unpublished agreements, credentials, or confidential diligence material.

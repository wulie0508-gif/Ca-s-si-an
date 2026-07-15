# Security

## Data handling

The deterministic audit core reads local documents and does not make network or model calls. Download helpers are separate and write only to the git-ignored `.cache/` directory.

Do not place non-public company records, personal contacts, contracts, credentials, API keys, or investment account data in manifests, examples, issues, or generated artifacts intended for sharing.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose user data or execute untrusted content. Contact the repository maintainer privately after a public maintainer contact is configured. Until then, do not use this alpha release on sensitive or untrusted documents.


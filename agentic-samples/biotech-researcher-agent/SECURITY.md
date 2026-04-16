# Security

## Disclaimer

This is a **demonstration application** — not intended for production use or clinical decision-making. All AI-generated outputs (hypotheses, analyses, literature summaries) require expert human review before use in any research or drug development decisions.

## Permission Model

Both `app.py` and `run.py` use `permission_mode="bypassPermissions"` to allow agents to execute tools (Bash, file I/O) without interactive approval. This is appropriate for local demo use in a sandboxed environment.

For production deployment, change to `permission_mode="requireApproval"` and implement an approval workflow.

## API Key Management

- Store your `ANTHROPIC_API_KEY` in a `.env` file (already in `.gitignore`)
- Set restrictive permissions: `chmod 600 .env`
- Never commit keys to version control
- Rotate keys if you suspect compromise — revoke immediately via the Anthropic console

## Data Classification

| Data Type | Classification | Handling |
|-----------|---------------|----------|
| `ANTHROPIC_API_KEY` | Restricted | `.env` file, never committed, `chmod 600` |
| `kras_inhibitor_assay.csv` | Public (simulated) | Included in repo — synthetic demo data, not real experimental results |
| AI-generated reports | Internal | Require human expert review before any external use |
| Agent logs / SSE streams | Internal | Access-logged via middleware, not persisted |

## Third-Party MCP Servers

This demo uses five MCP servers from the [Anthropic Life Sciences Marketplace](https://github.com/anthropics/life-sciences). Each accesses public biomedical databases:

| Server | Data Source | License |
|--------|-----------|---------|
| PubMed | NLM/NCBI | Public domain (US government work) |
| ChEMBL | EMBL-EBI | Creative Commons Attribution-ShareAlike 3.0 |
| ClinicalTrials | NLM/NCBI | Public domain (US government work) |
| bioRxiv | Cold Spring Harbor Laboratory | Preprints — individual article licenses vary |
| Open Targets | Open Targets consortium | Apache 2.0 |

Users are responsible for complying with each data source's terms of service.

## Web Application Security Controls

- Input validation: query length capped at 2000 characters (`Query(..., max_length=...)`)
- CORS: restricted to localhost origins only
- Concurrent run limit: max 5 simultaneous runs (429 on excess)
- Run IDs: cryptographically random (`secrets.token_urlsafe`)
- Error sanitization: internal errors logged server-side, generic message returned to client
- Access logging: HTTP middleware logs all requests
- CSP: meta tag restricts scripts/styles to self, connections to same origin

For production, deploy behind a reverse proxy (nginx, ALB) that terminates TLS.

## AI / ML Considerations

- Outputs are AI-generated hypotheses, not validated research conclusions
- The system may reflect biases present in the underlying literature and databases (publication bias, language bias, compound selection bias)
- All citations should be independently verified — the system is instructed to use real PMIDs/NCT IDs but verification is the user's responsibility
- Human-in-the-loop review is required before acting on any AI-generated recommendation

## Reporting Vulnerabilities

If you discover a security issue, please report it via the repository's issue tracker or contact the maintainers directly. Do not open a public issue for security vulnerabilities.

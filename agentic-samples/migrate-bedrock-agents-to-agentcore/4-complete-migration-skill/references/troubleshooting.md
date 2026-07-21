# Troubleshooting — long-form remediations

Load the section matching the symptom you hit. Symptoms are listed in SKILL.md's
review checklist so you recognize the trigger.

## CDK version pinning (deploy fails with cryptic schema/TS errors)

**Symptoms:** TS union mismatches on `HarnessConfig.tools[].type`; CDK "Cloud assembly
schema version … 54.0.0 … need CLI ≥ 2.1129.0"; or `Cannot find module
'@aws-cdk/cloud-assembly-schema'` after ad-hoc up/down installs.

**Root cause: version skew, not your code.** The scaffold's `agentcore/cdk/package.json`
uses `^` ranges (`@aws/agentcore-cdk`, `aws-cdk-lib`, `aws-cdk`) that resolve *newer*
than the installed CLI supports.

**Fix:** pin a self-consistent set, wipe `node_modules`+lockfile, and reinstall. The
constraint that matters: `@aws/agentcore-cdk`'s peer pins `aws-cdk-lib` (e.g. older
alphas → `^2.248.0` = assembly schema 53, readable by the CLI; newer alphas →
`^2.257.0` = schema 54, *not* readable by an older CLI). Pick the newest
`@aws/agentcore-cdk` whose peer keeps `aws-cdk-lib` at a schema your CLI reads
(`npm view @aws/agentcore-cdk@<v> peerDependencies`), pin `aws-cdk-lib` exact, and bump
the `aws-cdk` toolkit to match.

Validate with `agentcore deploy --dry-run` before the real deploy (no `-y` — keep the
confirmation prompt; don't let auto-approve habits leak into real deploys).

Also run `npm install` in `cdk/` at least once — the scaffold ships none.

## Local macOS SSL (`CERTIFICATE_VERIFY_FAILED` on token fetch)

This is local CA trust, not the service. Fix:

```bash
pip install certifi && export SSL_CERT_FILE=$(python -c "import certifi;print(certifi.where())")
```

(also `REQUESTS_CA_BUNDLE`). Scope the exports to the current shell session only —
don't persist them into shell profiles.

**Never "fix" this by disabling verification** (`verify=False`,
`NODE_TLS_REJECT_UNAUTHORIZED=0`, `--insecure`) — that trades a local trust issue for
a MITM hole. If certifi doesn't resolve it, you're likely behind a TLS-inspecting
corporate proxy: point `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` at the org's CA bundle
instead.

Doesn't occur in the Runtime Linux container.

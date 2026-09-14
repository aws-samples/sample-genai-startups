# Verified company research with an outer quality loop

> **Sample only:** This project demonstrates one way to structure and inspect
> an outer verification loop. It is not production-ready code. Before using
> this pattern in production, define and test your own ontology, source policy,
> verifier rules, security controls, operational limits, failure handling, and
> human-review process.

This sample tests an outer verification loop around an existing Claude Agent
SDK research loop. The native agent remains responsible for planning,
browsing, and producing a candidate. The application-owned outer loop decides
whether that candidate is ready to release, needs targeted recovery, or must
go to a person.

The sample uses five company fields:

- `name`
- `headquarters`
- `founded_year`
- `product_name`
- `product_description`

Each field contains a claim and immutable references to blocks from pages
captured during the run.

## Comparison flow

The paired demonstration sends one frozen candidate through two release paths.
It does not compare two independent research runs or establish a general
quality result.

```text
One bounded initial research run
  no acceptance contract
              |
              v
Freeze candidate, references, and captured pages
              |
        +-----+-------------------+
        |                         |
        v                         v
Native path                 Outer path
existing checks             deterministic gates
        |                    semantic verification
        v                         |
release unchanged           targeted recovery
                                  |
                                  v
                         accept or human review
```

Both paths start with exactly the same candidate. The native path releases it
after the existing schema and reference checks. The outer path applies the
workload-specific acceptance contract and may collect additional evidence.

## Outer-loop flow

The application owns the transitions:

```text
Validate JSON and evidence references
              |
              v
Verify each field independently
              |
       +------+------------------+
       |                         |
 all verified          insufficient or conflicting
       |                         |
       v                         v
    accept          keep conflicts open for review
                    queue insufficient fields
                                  |
                                  v
                    one deletion-only claim repair
                    when the verifier requests it
                                  |
                                  v
                    one reason-specific search
                    if support is still missing
                                  |
                                  v
                    reverify all unresolved fields
                                  |
                                  v
                    all verified? accept : review
```

The verifier returns one status per field:

- `verified`: admissible evidence explicitly supports the complete claim.
- `insufficient`: the submitted evidence does not meet the field rule.
- `conflicting`: admissible evidence explicitly asserts incompatible values.

A conflict does not prevent recovery of other fields. A search that produces
no useful evidence ends that field's attempt, not the entire workflow. The
final decision happens only after every insufficient field has received at
most one targeted attempt.

The whole record is accepted only when every field is verified. Otherwise the
workflow returns the package, unresolved fields, verifier reasons, and event
history for human review.

## Acceptance contract

The outer path accepts a record only when:

1. All five fields appear exactly once in valid JSON.
2. Every evidence reference resolves to a page and block captured in this run.
3. Every source satisfies the field-specific source policy.
4. Every selected block explicitly supports the field relationship and claim.
5. No field has unresolved conflicting evidence.

Code performs the deterministic checks. A fresh-context semantic verifier
applies the field rules to the submitted evidence.

The verifier has no browser or search tools. It receives only:

- Company identity
- Field and claim
- Canonical URL and source metadata
- Exact selected blocks
- Mechanical source-policy assessment

The targeted researcher owns browsing. It receives the unresolved fields,
their verifier reasons, current references, and URLs already checked.

## Evidence boundary

The browser wrapper captures a page before returning content to the model. It:

1. Stores the full page in application memory.
2. Computes a content-addressed `page_id`.
3. Splits the page into stable `block_id` values.
4. Returns bounded blocks to the researcher.

The model submits only `page_id` and `block_ids`:

```json
{
  "company_identity": "Acme Analytics",
  "fields": [
    {
      "field": "headquarters",
      "claim": "London, United Kingdom",
      "evidence": [
        {
          "page_id": "page_375785b084806594b41e",
          "block_ids": ["b0007"]
        }
      ]
    }
  ]
}
```

Application code resolves those references to canonical URL, title, and text
without refetching the page. Full snapshots are persisted with the run.

## Components

| Component | Responsibility |
|---|---|
| Initial researcher | Produce one complete candidate using the existing agent loop |
| Deterministic gate | Validate schema, source domains, page IDs, and block IDs |
| Semantic verifier | Judge field-level support using selected evidence only |
| Claim repairer | Remove unsupported parts without adding facts or changing the field |
| Targeted researcher | Run one verifier-directed search for an insufficient field |
| Python orchestrator | Enforce retries, stopping rules, acceptance, and handoff |
| Blinded reviewer | Assess both demonstration paths without seeing their labels |

The v12 live demonstration uses Opus 5 for initial research and Sonnet 5 for
verification, repair, targeted recovery, and blinded review. The v13
demonstration uses Opus 5 for every role. These are separate paired
demonstrations, not a model benchmark.

## Phase-1 scope

The sample implements a narrow part of a verification-centric research
architecture:

- Structured claims and references to captured evidence
- Deterministic evidence-integrity checks and semantic verification
- One deletion-only repair for an over-broad claim
- Verifier-directed, field-specific recovery
- Explicit acceptance or human-review outcomes

It does not implement durable planning, free-form claim revision, refutation
searches, source-lineage analysis, verifier calibration, adaptive stopping,
web-content security filtering, record-level consistency checking, or report
synthesis from accepted claims.

## Requirements to customize

Before adapting the sample, define:

- Required fields and ontology
- Acceptable source classes for each field
- Semantic support rules for each field
- Which outcomes are recoverable
- Which outcomes require human review
- Whether acceptance applies to each field or the complete record

The included ontology and source policy are illustrative.


## Project files

- `src/verified_company_research/contracts.py`: schemas and verdicts
- `src/verified_company_research/live_browser.py`: browser capture and blocks
- `src/verified_company_research/loop.py`: gates and state transitions
- `src/verified_company_research/paired_experiment.py`: live paired demonstration runner
- `src/verified_company_research/fixtures.py`: controlled scenarios
- `tests/`: deterministic and state-machine tests
- `.claude/skills/company-research/SKILL.md`: initial research skill
- `EXPERIMENT-PLAN.md`: protocol for a future multi-company evaluation
- `BLOG-DRAFT-OUTER-LOOP.md`: companion article
- `results/registrations/brompton-paired-v12.json`: mixed-model preregistration
- `results/live/brompton-paired-v12-20260910T142650Z-c1d02aea/`: mixed-model artifacts
- `results/registrations/brompton-paired-v13.json`: Opus-only preregistration
- `results/live/brompton-paired-v13-20260910T144006Z-979a482c/`: Opus-only artifacts

## Current limits

- One deletion-only repair and one targeted search per insufficient field are
  v1 policies.
- The verifier checks fields independently; it does not perform a final
  cross-field consistency check.
- The semantic verifier is another model judgment, not ground truth.
- The sample accepts or reviews the whole record; it does not publish partial
  results.

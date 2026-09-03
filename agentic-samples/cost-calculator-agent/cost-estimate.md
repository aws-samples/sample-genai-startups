# AWS Cost Estimate

> This is a sample output file. When you run the agent, it will generate a real estimate here.

## Project: [Your Project Name]

**Date**: YYYY-MM-DD  
**Region**: us-east-1  
**Estimated by**: AWS Cost Calculator Agent

---

## Architecture Overview

| Layer | Service | Configuration |
|-------|---------|---------------|
| Compute | ... | ... |
| Database | ... | ... |
| Storage | ... | ... |
| Networking | ... | ... |

---

## Monthly Cost Breakdown

| Service | Configuration | Monthly Cost |
|---------|---------------|--------------|
| | | |
| **Total** | | **$X,XXX.XX** |

---

## Annual Cost Estimate

| Pricing Model | Annual Cost | Savings |
|---------------|-------------|---------|
| On-Demand | $XX,XXX | — |
| 1-Year Reserved/Savings Plan | $XX,XXX | XX% |
| 3-Year Reserved/Savings Plan | $XX,XXX | XX% |

---

## Cost Optimization Recommendations

1. ...
2. ...
3. ...

---

## AWS Pricing Calculator

**Shareable URL**: [Generated automatically via Nova Act]

The estimate-config.json was used to automate the AWS Pricing Calculator and generate a public shareable link. All services are pre-populated with the exact configurations discussed.

To regenerate: `python generate_calculator_url.py estimate-config.json`

---

## Assumptions & Caveats

- Pricing based on [region] rates as of [date]
- Does not include data transfer between AZs (typically small)
- Free tier benefits not included (assumes expired)
- Actual costs may vary based on usage patterns

---
title: "Lab 1: Data Preparation"
weight: 30
---

# Lab 1: Data Preparation

## What you will learn

- How real user queries are extracted from PostgreSQL's `pg_stat_statements`
- How Amazon Bedrock generates natural language descriptions for each query
- The difference between SFT and RLVR dataset formats
- How the SageMaker AI Registry provides versioned, ARN-addressable datasets

---

## Get started

1. In the JupyterLab file browser, open **`01-data-preparation.ipynb`**.

2. Run all cells in order. The notebook is structured in three parts:
   - **Setup** — restore variables from Lab 0 via `%store -r`, then run the cells that define the pipeline's helper functions. These do not touch the database.
   - **The pipeline, in seven explicit steps** — extract, clean, extract schema, format for SFT, split, format for RLVR, validate. Each step has a preview cell that prints what it produced.
   - **Registration** — register all six datasets in the SageMaker AI Registry.

3. **Read the preview cells.** They are the reason the pipeline is split into steps rather than run as one call: you should finish this lab having seen your own training pairs, your own SFT record, and your own RLVR records — not just a summary count. The most valuable one is the Step 2 preview, which shows the `user_query` → `expected_sql` pairing that everything downstream is built on.

4. Step 2 takes approximately **10 minutes**. It processes ~240 queries through Bedrock for repair and natural language generation, executing each candidate against Aurora to verify it. Every other step completes in seconds. Watch for the summary output at Step 7:
   ```
   ======================================================================
   PIPELINE SUMMARY
   ======================================================================
     Raw queries extracted:    241
     After cleaning:           241

     Files on disk:
       SFT train           204 records  ./train.jsonl
       SFT validation       37 records  ./validation.jsonl
       SFT combined        241 records  ./combined.jsonl
       RLVR train          204 records  ./rlvr_data/rl_train.jsonl
       RLVR validation      37 records  ./rlvr_data/rl_val.jsonl
       RLVR combined       241 records  ./rlvr_data/rl_combined.jsonl

     SFT JSONL valid:          PASS
     RLVR JSONL valid:         PASS
   ```

   The record counts are read back off disk rather than from memory, so this is also the check that no file was truncated before upload. Your own counts will differ — they depend on how many queries `pg_stat_statements` recorded and how many survived cleaning.

5. After the pipeline completes, the dataset registration cell creates 6 versioned datasets. Verify all ARNs print successfully.

---

## Output files

| File | Format | Purpose |
|------|--------|---------|
| `train.jsonl` | SFT | Training split (~85%) |
| `validation.jsonl` | SFT | Held-out evaluation (~15%) |
| `combined.jsonl` | SFT | Full dataset (train + val) |
| `rlvr_data/rl_train.jsonl` | RLVR | Training split for RL |
| `rlvr_data/rl_val.jsonl` | RLVR | Validation split for RL |
| `rlvr_data/rl_combined.jsonl` | RLVR | Full dataset for RL |

---

## Why two formats?

- **SFT** uses `{"prompt": "...", "completion": "..."}` — the model learns by imitating the completion directly.
- **RLVR** uses `{"prompt": [messages], "reward_model": {"ground_truth": "..."}}` — the model generates its own completions and learns from execution feedback.

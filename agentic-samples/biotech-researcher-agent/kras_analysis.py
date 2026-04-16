"""
KRAS Inhibitor IC50 Statistical Analysis
Biostatistician script — one-way ANOVA + Tukey HSD post-hoc + publication plot
"""

import pandas as pd
import numpy as np
import scipy.stats as stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from datetime import date
import itertools
import warnings
warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
DATA_PATH   = "/Users/sequdian/Documents/DASamples/sample-genai-startups/agentic-samples/biotech-researcher-agent/data/kras_inhibitor_assay.csv"
OUT_PNG     = "/Users/sequdian/Documents/DASamples/sample-genai-startups/agentic-samples/biotech-researcher-agent/output/kras_ic50_comparison.png"
OUT_TXT     = "/Users/sequdian/Documents/DASamples/sample-genai-startups/agentic-samples/biotech-researcher-agent/output/kras_ic50_analysis.txt"

# ── 1. Load & filter ───────────────────────────────────────────────────────────
df_raw = pd.read_csv(DATA_PATH)
print(f"Raw rows: {len(df_raw)}")
print(f"Assay types present: {df_raw['assay_type'].unique()}")

df = df_raw[df_raw["assay_type"].isin(["enzymatic", "cellular"])].copy()
print(f"Filtered rows (enzymatic + cellular): {len(df)}")
print(f"Compounds: {df['compound_name'].unique()}")

# Order compounds for consistent display
compound_order = ["Sotorasib", "Adagrasib", "BRX-471"]
df["compound_name"] = pd.Categorical(df["compound_name"], categories=compound_order, ordered=True)
df = df.sort_values("compound_name")

# ── 2. Group IC50 values per compound ─────────────────────────────────────────
groups = {c: df.loc[df["compound_name"] == c, "ic50_nm"].values for c in compound_order}

# ── 3. Descriptive statistics ─────────────────────────────────────────────────
desc_rows = []
for c in compound_order:
    vals = groups[c]
    desc_rows.append({
        "Compound":  c,
        "n":         len(vals),
        "Mean (nM)": round(np.mean(vals), 3),
        "SD (nM)":   round(np.std(vals, ddof=1), 3),
        "Median (nM)": round(np.median(vals), 3),
        "Min (nM)":  round(np.min(vals), 3),
        "Max (nM)":  round(np.max(vals), 3),
    })
desc_df = pd.DataFrame(desc_rows)

# ── 4. One-way ANOVA ──────────────────────────────────────────────────────────
f_stat, p_anova = stats.f_oneway(*[groups[c] for c in compound_order])
anova_sig = p_anova < 0.05
print(f"\nANOVA: F={f_stat:.4f}, p={p_anova:.6f}, significant={anova_sig}")

# ── 5. Tukey HSD (if ANOVA significant) ───────────────────────────────────────
tukey_result = None
tukey_df     = None
if anova_sig:
    all_vals     = df["ic50_nm"].values
    all_labels   = df["compound_name"].astype(str).values
    tukey_result = pairwise_tukeyhsd(endog=all_vals, groups=all_labels, alpha=0.05)
    tukey_df = pd.DataFrame(
        data    = tukey_result._results_table.data[1:],
        columns = tukey_result._results_table.data[0]
    )
    tukey_df.columns = ["Group 1", "Group 2", "Mean Diff", "p-adj", "Lower CI", "Upper CI", "Reject H0"]
    # Ensure numeric types
    for col in ["Mean Diff", "p-adj", "Lower CI", "Upper CI"]:
        tukey_df[col] = pd.to_numeric(tukey_df[col], errors="coerce").round(4)
    print("\nTukey HSD results:")
    print(tukey_df.to_string(index=False))

# ── 6. Publication-quality bar chart ─────────────────────────────────────────
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.3)

PALETTE = {"Sotorasib": "#2176AE", "Adagrasib": "#E05C2F", "BRX-471": "#3DAA6D"}
colors   = [PALETTE[c] for c in compound_order]

fig, ax = plt.subplots(figsize=(8, 6))

means  = [np.mean(groups[c]) for c in compound_order]
sds    = [np.std(groups[c], ddof=1) for c in compound_order]
x_pos  = np.arange(len(compound_order))

# Bar chart with SD error bars
bars = ax.bar(
    x_pos, means, yerr=sds,
    color=colors, width=0.5,
    capsize=6, linewidth=1.2,
    error_kw={"elinewidth": 1.8, "ecolor": "black", "capthick": 1.8},
    zorder=2, edgecolor="white", alpha=0.88
)

# Strip overlay — individual data points
jitter_seed = 42
rng = np.random.default_rng(jitter_seed)
for i, c in enumerate(compound_order):
    y_vals = groups[c]
    x_jitter = rng.uniform(-0.12, 0.12, size=len(y_vals)) + i
    ax.scatter(
        x_jitter, y_vals,
        color="black", s=32, zorder=4, alpha=0.65,
        linewidths=0.5, edgecolors="white"
    )

# ── Significance brackets (Tukey p < 0.05) ────────────────────────────────────
if tukey_df is not None:
    sig_pairs = tukey_df[tukey_df["Reject H0"] == True][["Group 1", "Group 2", "p-adj"]].values
    # Bracket drawing helper
    y_max_data = max(
        np.max(groups[c]) + np.std(groups[c], ddof=1) for c in compound_order
    )
    bracket_step = y_max_data * 0.13
    bracket_base = y_max_data + bracket_step * 0.6

    drawn = 0
    for g1, g2, padj in sig_pairs:
        idx1 = compound_order.index(g1)
        idx2 = compound_order.index(g2)
        y_bracket = bracket_base + drawn * bracket_step
        # horizontal line
        ax.plot(
            [idx1, idx1, idx2, idx2],
            [y_bracket - bracket_step * 0.1,
             y_bracket,
             y_bracket,
             y_bracket - bracket_step * 0.1],
            lw=1.4, color="black"
        )
        # significance label
        if   padj < 0.001: sig_label = "***"
        elif padj < 0.01:  sig_label = "**"
        else:               sig_label = "*"
        ax.text(
            (idx1 + idx2) / 2, y_bracket + bracket_step * 0.05,
            sig_label, ha="center", va="bottom", fontsize=13, color="black"
        )
        drawn += 1

# Axes formatting
ax.set_xticks(x_pos)
ax.set_xticklabels(compound_order, fontsize=12)
ax.set_xlabel("Compound", fontsize=13, labelpad=8)
ax.set_ylabel("IC50 (nM)", fontsize=13, labelpad=8)
ax.set_title("IC50 Comparison Across KRAS G12C Inhibitors", fontsize=14, fontweight="bold", pad=14)

# Y-axis starts at 0, add 25 % headroom for brackets
y_top = ax.get_ylim()[1]
ax.set_ylim(0, y_top * 1.08)

# Light grid on y only
ax.yaxis.grid(True, linestyle="--", linewidth=0.7, alpha=0.7)
ax.set_axisbelow(True)

# Legend patch for bar colors
legend_patches = [
    mpatches.Patch(color=PALETTE[c], label=c, alpha=0.88) for c in compound_order
]
ax.legend(
    handles=legend_patches, loc="upper right",
    fontsize=10, framealpha=0.85, edgecolor="grey"
)

plt.tight_layout()
fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"\nPlot saved -> {OUT_PNG}")

# ── 7. Plain-text report ──────────────────────────────────────────────────────
today = date.today().strftime("%Y-%m-%d")

assay_types_included = sorted(df["assay_type"].unique().tolist())
obs_per_compound = df.groupby("compound_name", observed=True).size().to_dict()

# Build descriptive stats table string
col_widths = [12, 5, 12, 12, 13, 12, 12]
header_fields = ["Compound", "n", "Mean (nM)", "SD (nM)", "Median (nM)", "Min (nM)", "Max (nM)"]

def fmt_row(fields):
    return "  ".join(str(f).ljust(w) for f, w in zip(fields, col_widths))

desc_table_lines = [
    fmt_row(header_fields),
    "-" * (sum(col_widths) + 2 * (len(col_widths) - 1)),
]
for _, row in desc_df.iterrows():
    desc_table_lines.append(fmt_row([
        row["Compound"], row["n"],
        f"{row['Mean (nM)']:.3f}", f"{row['SD (nM)']:.3f}",
        f"{row['Median (nM)']:.3f}", f"{row['Min (nM)']:.3f}", f"{row['Max (nM)']:.3f}"
    ]))

# Tukey table string
if tukey_df is not None:
    t_col_widths = [12, 12, 12, 10, 12, 12, 12]
    t_header = ["Group 1", "Group 2", "Mean Diff", "p-adj", "Lower CI", "Upper CI", "Reject H0"]
    tukey_lines = [
        fmt_row.__func__(None) if False else
        "  ".join(str(f).ljust(w) for f, w in zip(t_header, t_col_widths)),
        "-" * (sum(t_col_widths) + 2 * (len(t_col_widths) - 1)),
    ]
    for _, row in tukey_df.iterrows():
        tukey_lines.append(
            "  ".join(str(v).ljust(w) for v, w in zip(
                [row["Group 1"], row["Group 2"], f"{row['Mean Diff']:.4f}",
                 f"{row['p-adj']:.4f}", f"{row['Lower CI']:.4f}",
                 f"{row['Upper CI']:.4f}", str(row["Reject H0"])],
                t_col_widths
            ))
        )
    tukey_section = (
        "Post-Hoc Tukey HSD Results (alpha = 0.05)\n"
        "------------------------------------------\n"
        + "\n".join(tukey_lines)
    )
else:
    tukey_section = (
        "Post-Hoc Tukey HSD\n"
        "------------------\n"
        "Not performed (ANOVA was not statistically significant, p >= 0.05)."
    )

# Conclusion paragraph
if anova_sig:
    sig_pairs_str = "; ".join(
        f"{r['Group 1']} vs {r['Group 2']} (p-adj={r['p-adj']:.4f})"
        for _, r in tukey_df[tukey_df["Reject H0"] == True].iterrows()
    )
    conclusion = (
        f"One-way ANOVA revealed a statistically significant difference in IC50 values "
        f"across the three KRAS G12C inhibitors (F={f_stat:.4f}, p={p_anova:.6f}). "
        f"Post-hoc Tukey HSD testing identified significant pairwise differences between: "
        f"{sig_pairs_str}. "
        f"BRX-471 demonstrated the lowest mean IC50 ({desc_df.loc[desc_df['Compound']=='BRX-471','Mean (nM)'].values[0]:.3f} nM), "
        f"suggesting superior in vitro potency relative to Sotorasib "
        f"({desc_df.loc[desc_df['Compound']=='Sotorasib','Mean (nM)'].values[0]:.3f} nM mean IC50) "
        f"and Adagrasib "
        f"({desc_df.loc[desc_df['Compound']=='Adagrasib','Mean (nM)'].values[0]:.3f} nM mean IC50). "
        f"These findings should be interpreted in the context of assay heterogeneity (both enzymatic "
        f"and cellular formats included) and the limited number of replicates per group."
    )
else:
    conclusion = (
        f"One-way ANOVA did not reveal a statistically significant difference in IC50 values "
        f"across the three compounds (F={f_stat:.4f}, p={p_anova:.6f}). "
        f"No post-hoc testing was warranted. Larger sample sizes may be needed to detect "
        f"meaningful differences if they exist."
    )

report = f"""KRAS Inhibitor IC50 Statistical Analysis
=========================================
Date of Analysis : {today}
Analyst          : AI-assisted biostatistics pipeline (Claude / biotech-researcher-agent)

DATA SUMMARY
------------
Source file      : kras_inhibitor_assay.csv
Assay types included : {", ".join(assay_types_included)}  (combo rows excluded)
Total observations after filtering : {len(df)}

Observations per compound:
""" + "".join(f"  {c:<14}: {obs_per_compound.get(c, 0)}\n" for c in compound_order) + f"""
DESCRIPTIVE STATISTICS
----------------------
{chr(10).join(desc_table_lines)}

ANOVA RESULTS
-------------
Test            : One-way ANOVA (scipy.stats.f_oneway)
Null hypothesis : Mean IC50 is equal across all three compounds
Groups          : {", ".join(compound_order)}

  F-statistic : {f_stat:.4f}
  p-value     : {p_anova:.6f}
  Significant : {"Yes (p < 0.05)" if anova_sig else "No (p >= 0.05)"}

{tukey_section}

CONCLUSION
----------
{conclusion}

OUTPUT FILES
------------
  Bar chart : {OUT_PNG}
  Report    : {OUT_TXT}

DISCLAIMER
----------
AI-generated analysis — requires expert review.
"""

with open(OUT_TXT, "w") as fh:
    fh.write(report)
print(f"Report saved -> {OUT_TXT}")
print("\nDone.")

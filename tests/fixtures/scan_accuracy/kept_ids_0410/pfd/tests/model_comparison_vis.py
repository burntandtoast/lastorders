# excerpt: Sam-Osian/PFD-toolkit tests/model_comparison_vis.py, lines 65-66 and 111-112
# Baseline references (optional)
FRONTIER_NAMES = {"gpt-4.1": "GPT-4.1"}


def refs(df):
    return df[df["model"].isin(FRONTIER_NAMES.keys())]

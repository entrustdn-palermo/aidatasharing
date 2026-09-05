# Cross-org pooled aggregates with a contributor minimum

Regional comparisons and crop-classification Model training are only valuable if they pool data across organizations — a single organization will rarely have enough agricultural data for a meaningful yield average or a trainable classifier. We therefore pool every Contributing Dataset across organizations into a single anonymous pool that feeds both Regional Aggregates and Model training, and we never show a Regional Aggregate for a region+crop until it has at least five contributing datasets (the Contributor Minimum).

## Considered Options

- **Org-only pooling** — rejected: pools stay too small to compare or train on; the feature would be dead on arrival for small organizations.
- **Cross-org pooling without a minimum** — rejected: with 2–4 contributors in a region+crop, the aggregate itself de-anonymizes members (a lone outlier farmer is identifiable by subtraction).
- **Separate consent regimes for aggregates vs. training** — rejected: two policies for one pool would confuse members and double the enforcement code; one pool means one policy.

## Consequences

- Qualifying as a Contributing Dataset is the single consent act: tagging a dataset with Region, Crop, and Yield Column feeds both comparisons and training. There is no separate "share for training" toggle in v1.
- Ticket #4 additionally requires Season on an agri-tagged upload, so the implemented qualification is Region + Crop + Season + Yield Column. This narrows consent slightly beyond the three tags considered here; aggregates are meaningless without a season anyway, so the extra tag is treated as part of the same consent act rather than a second regime.
- Aggregate and model responses must never expose individual rows or contributors — only pooled statistics — regardless of Sharing Level, which continues to govern the dataset itself, not the pool.
- Raising the Contributor Minimum is safe; lowering it below five later re-opens the de-anonymization window and should be treated as a privacy decision, not a tuning change.

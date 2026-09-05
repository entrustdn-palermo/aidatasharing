# Simple AI Sharing

A platform where users upload datasets into organizations, share them at private/organization/public levels, chat with AI agents over the data, and consume MindsDB-backed AI processing.

## Language

**Dataset**:
A collection of one or more uploaded files, owned by an organization, with derived schema and quality metadata. The central artifact of the platform.
_Avoid_: upload, data set

**Dataset File**:
A single file belonging to a dataset. The primary file is the one processed for schema, preview, and AI features.
_Avoid_: attachment

**Sharing Level**:
The visibility policy on a dataset: `private` (owner only), `organization` (all org members), or `public` (anyone with a share link).
_Avoid_: visibility, access level

**Share Link**:
A token-based URL (optionally password-protected) granting access to a shared dataset.
_Avoid_: public link, invite

**Organization**:
The owning entity for users and datasets. All access flows through organization membership.
_Avoid_: workspace, tenant

**Member**:
A user belonging to an organization, holding one of the roles: owner, admin, manager, member, viewer. A farmer is simply a member who uploads agricultural data.
_Avoid_: farmer (as a role), contributor (as a role)

**AI Processing**:
The pipeline run over a dataset after upload (agent setup, status tracking), producing a chat-capable agent.
_Avoid_: indexing, embedding

**Model**:
A MindsDB predictive model trained on a dataset, tracked with target/feature columns, accuracy, and training status.
_Avoid_: agent, AI (when meaning the predictive model)

**Season**:
The growing season a dataset's agricultural records cover, captured at upload.
_Avoid_: period, harvest year

## Agricultural Data

**Region**:
An administrative area from the platform's managed reference list, used to pool datasets for comparison. Province-level in v1; farmers select it from a dropdown, never type it.
_Avoid_: location, area, province (region is the umbrella term)

**Crop**:
A crop type from the managed reference list that a dataset's records concern.
_Avoid_: commodity, plant type

**Yield Column**:
The numeric column in a dataset's primary file that the user identifies in the wizard as the yield measurement. The single comparison metric in v1 is yield per hectare.
_Avoid_: target column (that means a Model's prediction target), metric

**Regional Aggregate**:
An anonymized pooled statistic (yield per hectare) computed across contributing datasets sharing a region and crop; shown only when the Contributor Minimum is met.
_Avoid_: benchmark, regional average

**Contributor Minimum**:
The smallest number of contributing datasets (five in v1) required before a Regional Aggregate is shown for a region and crop. Prevents de-anonymizing a lone contributor.
_Avoid_: threshold, quorum

**Contributing Dataset**:
A dataset whose region, crop, and yield data qualify it to feed both Regional Aggregates and Model training. One pool, one consent policy.
_Avoid_: shared dataset (that means link sharing)

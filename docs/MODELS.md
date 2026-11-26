# Models and model profiles

Vibe manages models from multiple providers and enables role-based assignment through model profiles. A **model profile** maps models to roles, such as coder and reviewer.

## Model overview

The model table provides an overview and assessment of available models. It includes:

- Model ID
- Provider
- Availability
- Context size
- Image support
- Strengths and weaknesses
- Speed
- Effort
- Data terms
- Price

Unknown values are explicitly marked as unknown. Vibe does not invent model IDs or capabilities.

## Facts, measurements, and assessments

Vibe distinguishes facts, measurements, user reports, and assessments. Where applicable, it provides the source, date, and test method.

Stale information is marked as stale. Old assessments or prices are not copied without verification.

## Pricing

Prices specify currency, unit, input and output rates, and effective date. Cache pricing, tiers, and surcharges are displayed separately.

## Model profiles

Model profiles can be created, edited, copied, deleted, and applied. They support configurable roles, including at least coder and reviewer, mapped to global or project agents.

When applying a profile:

- The exact changes are previewed before writing.
- All target agents and models are validated before the first write.
- Applying a profile is transactional or fully reversible after partial failure.
- An empty profile must not report successful application.

## Detecting drift

If later manual edits cause agents to differ from a profile, Vibe makes that visible.

## Cost and paid models

Paid profiles are clearly identified. Vibe never automatically switches from a free model to a paid model.

Credentials do not belong in agent files or this repository. Vibe distinguishes between a listed model and a model the user is authorized to use.

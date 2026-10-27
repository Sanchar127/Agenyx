# Input Guardrails Configuration

Agenyx input guardrails are configured through a versioned `GuardrailsRecipe`.
The Go `recipe` package owns YAML decoding and schema validation. The Go
`internal/guardrails` package selects the recipe, resolves required environment
placeholders, validates the effective configuration, and exposes it through
a read-only configuration API.

Loading and validating configuration does not execute detectors. Detection,
model inference, and enforcement are separate responsibilities.

## Selecting a recipe

The canonical default recipe is:

`recipes/guardrails/input/default.yaml`

Set `AGENEYX_GUARDRAILS_RECIPE` to select another recipe file:

```sh
export AGENEYX_GUARDRAILS_RECIPE=/path/to/your/guardrails.yaml

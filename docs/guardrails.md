# Input Guardrails Configuration

Agenyx input guardrails are configured with a versioned `GuardrailsRecipe`.
The Go `recipe` package owns recipe decoding and schema validation. Detection
and model inference are separate responsibilities and are not implemented by
the configuration schema.

## Configuration example

See [`recipes/guardrails/default.yaml`](../recipes/guardrails/default.yaml)
for the complete default recipe.

## Schema

### Input

| Field | Type | Meaning |
|---|---|---|
| `input.enabled` | boolean | Enables or disables input guardrails. |
| `input.onError` | `block` or `allow` | Legacy input-stage error policy, retained for compatibility. |
| `input.maxInputLength` | positive integer | Maximum input length supported by the policy contract. |
| `input.detectors` | list | Detector definitions. |

Supported detector types are `prompt-injection`, `jailbreak`, and `pii`.
Duplicate detector types are rejected.

Each detector has:

| Field | Meaning |
|---|---|
| `type` | Supported detector identifier. |
| `enabled` | Enables or disables that detector. |
| `provider` | `pattern` or `classifier`. |
| `onViolation` | `block`, `warn`, or `redact`. |
| `categories` | PII categories; required for an enabled PII detector. |
| `patterns` | Reserved for pattern-based detector configuration. |

`redact` is currently permitted only for PII. This schema declaration does not
implement redaction; the enforcement pipeline must implement it before the
action is considered operational.

Supported PII categories are `email`, `phone`, `ip-address`, and `credit-card`.

### Execution

- `execution.timeoutMs`: positive integer defining the overall execution
  timeout budget.
- `execution.maxConcurrentChecks`: positive integer defining the configured
  concurrency limit.

These fields define the configuration contract. Enforcement of the timeout and
concurrency limit belongs to the future guardrails execution engine.

### Model runtime

- `modelRuntime.endpoint`: non-empty endpoint when an enabled detector uses
  the `classifier` provider.
- `modelRuntime.protocol`: currently `http`.
- `modelRuntime.timeoutMs`: positive timeout in milliseconds.

The default recipe uses `${GUARDRAILS_MODEL_URL}` as an environment placeholder.
The current recipe loader does not expand environment placeholders. The future
model-runtime integration must resolve the placeholder safely and reject an
unset or invalid endpoint before making requests.

Do not put credentials or other secrets in recipe files. Configure sensitive
values through an appropriate secret or environment mechanism.

### Failure policy

`failurePolicy.onDetectorError` and `failurePolicy.onTimeout` each accept:

- `block`: fail closed when a detector errors or times out.
- `allow`: fail open and continue when a detector errors or times out.

Fail-open behavior is an explicit availability-versus-security trade-off.
Production deployments should select it deliberately.

`input.onError` is retained for compatibility with the existing schema. It
describes the input-stage error policy; `failurePolicy` describes detector
errors and timeouts. Runtime behavior must be implemented and tested by the
execution-engine work.

## Versioning and validation

The recipe uses the shared Agenyx envelope:

- `apiVersion: agenyx.ai/v1alpha1`
- `kind: GuardrailsRecipe`
- `metadata.name`
- `spec`

The shared loader rejects unsupported API versions, empty recipe names,
unknown spec fields, and multiple YAML documents. `GuardrailsSpec.Validate`
checks supported detector types, duplicate detectors, provider and action
values, PII categories, execution limits, model-runtime settings when needed,
and failure policies for enabled input guardrails.

Output guardrails are outside the scope of this initial schema. Future output
configuration should be introduced compatibly rather than changing the
meaning of existing input fields.

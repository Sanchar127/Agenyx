# Contributing

Thanks for your interest in contributing to the Distributed AI Agent Runtime. This document covers how to propose changes, the standards we hold code to, and where to start if you're new to the project.

## Before you start

- Check open [issues](../../issues) and [pull requests](../../pulls) to avoid duplicating work.
- For anything larger than a small fix — a new component, a change to the orchestration model, a new tool sandbox backend — open an issue first to discuss the approach before writing code. This saves you from building something that doesn't fit the project's direction.
- Small fixes (typos, docs, small bugs) can go straight to a pull request.

## Development setup

```bash
git clone https://github.com/<your-org>/<your-repo>.git
cd <your-repo>
cp .env.example .env
docker compose up
```

See [`docs/local-dev.md`](docs/local-dev.md) for the full local environment setup, including how to run individual services outside Docker for faster iteration.

## Making a change

1. Fork the repository and create a branch off `main`:
   ```bash
   git checkout -b your-name/short-description
   ```
2. Make your change. Keep pull requests focused — one logical change per PR is easier to review and revert if needed.
3. Add or update tests. Changes to the orchestrator, agent worker, or tool sandbox require test coverage; changes to docs or config do not.
4. Run the test suite locally before opening a PR:
   ```bash
   make test
   ```
5. Update relevant documentation (`README.md`, `docs/`) if your change affects setup, architecture, or public behavior.
6. Open a pull request against `main` with a clear description of what changed and why. Link the related issue if one exists.

## Code standards

- Follow the existing style and structure within each service directory — the gateway, orchestrator, agent worker, and tool sandbox are separate services and may have different language conventions; match what's already there rather than introducing a new pattern.
- Run linters and formatters before committing:
  ```bash
  make lint
  make format
  ```
- Public functions and API endpoints should have docstrings/comments explaining intent, not just restating the signature.
- Avoid adding new infrastructure dependencies (databases, queues, external services) without discussing it in an issue first — see "Design principles" in the README. The project intentionally keeps the default stack minimal.

## Security-sensitive areas

The tool sandbox and any code touching authentication, tenant isolation, or the sandbox's network/resource limits are treated as security-sensitive.

- Do not weaken sandbox isolation defaults (network egress, resource limits, execution timeouts) without an explicit discussion and review from a maintainer.
- Do not commit credentials, API keys, or tokens, even in test fixtures. Use the `.env.example` pattern and document any new environment variables there.
- If you discover a security vulnerability, do not open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure instructions.

## Commit messages

Use clear, present-tense commit messages:

```
Add checkpointing to orchestrator task loop
Fix race condition in agent worker task claim
Update tool sandbox docs for Firecracker setup
```

Avoid vague messages like "fix stuff" or "wip" in the final PR — squash or clean up your commit history before requesting review if needed.

## Pull request review

- PRs require at least one maintainer approval before merging.
- CI must pass (lint, tests, build) before a PR is merged.
- Maintainers may ask for changes related to architectural fit, not just correctness — a change can be technically correct and still not fit the project's direction, and we'll explain why if that happens.
- Be patient — this is a part-time-maintained project and review may take a few days.

## Reporting bugs

Open an issue with:
- A clear description of the expected vs actual behavior
- Steps to reproduce
- Relevant logs or error output
- Which component is affected (gateway, orchestrator, agent worker, tool sandbox, inference, infra)

## Suggesting features

Open an issue describing the problem you're trying to solve, not just the feature itself — this helps us evaluate whether it fits the project's scope and design principles, or whether an existing component already solves it.

## Code of conduct

Be respectful and constructive in issues, pull requests, and discussions. Disagreements about technical direction are normal and welcome; personal attacks are not.

## Questions

If something in this guide is unclear, open an issue with the `question` label — improving this document based on real questions is itself a welcome contribution.

// Package eval provides the Agenyx evaluation and benchmarking platform.
//
// The evaluation platform is operationally isolated from the production
// inference and agent request paths. It uses independently scalable workers
// and a separate job queue to ensure evaluation workloads never interfere
// with production workloads.
//
// The platform is model-independent: the same evaluation can run against any
// registered model/provider without code changes.
//
// Package layout:
//
//	config     - Typed configuration for the evaluation API and scheduler
//	models     - Core data models (Evaluation, Run, Job, Model, Provider, etc.)
//	store      - PostgreSQL data access layer
//	api        - HTTP API handlers
//	scheduler  - Job scheduler and execution planner
//	server     - HTTP server setup
package eval

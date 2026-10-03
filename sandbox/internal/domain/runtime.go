package domain

import "context"

// Runtime provides the execution boundary between the control plane
// and the underlying sandbox isolation technology.
//
// Implementations may use gVisor, Firecracker, or another runtime.
// Runtime implementations must not mutate Sandbox or Execution domain state.
type Runtime interface {
	// Create provisions the runtime resources required for a sandbox.
	// A successful return means the sandbox has been provisioned,
	// but lifecycle state transitions remain the responsibility of
	// the control plane.
	Create(ctx context.Context, sandbox Sandbox, spec SandboxSpec) error

	// Execute runs a command inside an existing sandbox.
	//
	// A successfully executed process returns an ExecutionResult and
	// a nil error, even when the process exits with a non-zero exit code.
	//
	// Runtime failures are returned as errors. Context cancellation
	// and deadline errors are propagated to the caller.
	Execute(
		ctx context.Context,
		sandboxID SandboxID,
		command string,
		args []string,
	) (ExecutionResult, error)

	// Stop stops the runtime resources associated with a sandbox.
	Stop(ctx context.Context, sandboxID SandboxID) error

	// Delete removes the runtime resources associated with a sandbox.
	Delete(ctx context.Context, sandboxID SandboxID) error
}

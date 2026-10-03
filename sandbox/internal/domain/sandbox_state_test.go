package domain

import "testing"

func TestSandboxStateIsTerminal(t *testing.T) {
	tests := []struct {
		name  string
		state SandboxState
		want  bool
	}{
		{
			name:  "completed is terminal",
			state: SandboxStateCompleted,
			want:  true,
		},
		{
			name:  "failed is terminal",
			state: SandboxStateFailed,
			want:  true,
		},
		{
			name:  "deleted is terminal",
			state: SandboxStateDeleted,
			want:  true,
		},
		{
			name:  "requested is not terminal",
			state: SandboxStateRequested,
			want:  false,
		},
		{
			name:  "creating is not terminal",
			state: SandboxStateCreating,
			want:  false,
		},
		{
			name:  "ready is not terminal",
			state: SandboxStateReady,
			want:  false,
		},
		{
			name:  "executing is not terminal",
			state: SandboxStateExecuting,
			want:  false,
		},
		{
			name:  "stopping is not terminal",
			state: SandboxStateStopping,
			want:  false,
		},
		{
			name:  "stopped is not terminal",
			state: SandboxStateStopped,
			want:  false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.state.IsTerminal(); got != tt.want {
				t.Fatalf(
					"IsTerminal() = %v, want %v",
					got,
					tt.want,
				)
			}
		})
	}
}

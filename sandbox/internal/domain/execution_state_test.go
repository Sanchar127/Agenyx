package domain

import "testing"

func TestExecutionStateIsTerminal(t *testing.T) {
	tests := []struct {
		state ExecutionState
		want  bool
	}{
		{
			state: ExecutionStateRequested,
			want:  false,
		},
		{
			state: ExecutionStateRunning,
			want:  false,
		},
		{
			state: ExecutionStateCompleted,
			want:  true,
		},
		{
			state: ExecutionStateFailed,
			want:  true,
		},
		{
			state: ExecutionStateTimeout,
			want:  true,
		},
	}

	for _, tt := range tests {
		t.Run(string(tt.state), func(t *testing.T) {
			got := tt.state.IsTerminal()

			if got != tt.want {
				t.Fatalf(
					"IsTerminal() = %v, want %v",
					got,
					tt.want,
				)
			}
		})
	}
}

func TestExecutionStateCanTransitionTo(t *testing.T) {
	tests := []struct {
		name string
		from ExecutionState
		to   ExecutionState
		want bool
	}{
		{
			name: "requested to running",
			from: ExecutionStateRequested,
			to:   ExecutionStateRunning,
			want: true,
		},
		{
			name: "running to completed",
			from: ExecutionStateRunning,
			to:   ExecutionStateCompleted,
			want: true,
		},
		{
			name: "running to failed",
			from: ExecutionStateRunning,
			to:   ExecutionStateFailed,
			want: true,
		},
		{
			name: "running to timeout",
			from: ExecutionStateRunning,
			to:   ExecutionStateTimeout,
			want: true,
		},
		{
			name: "requested cannot skip running",
			from: ExecutionStateRequested,
			to:   ExecutionStateCompleted,
			want: false,
		},
		{
			name: "requested cannot fail directly",
			from: ExecutionStateRequested,
			to:   ExecutionStateFailed,
			want: false,
		},
		{
			name: "running cannot go back to requested",
			from: ExecutionStateRunning,
			to:   ExecutionStateRequested,
			want: false,
		},
		{
			name: "completed cannot transition",
			from: ExecutionStateCompleted,
			to:   ExecutionStateRunning,
			want: false,
		},
		{
			name: "failed cannot transition",
			from: ExecutionStateFailed,
			to:   ExecutionStateRunning,
			want: false,
		},
		{
			name: "timeout cannot transition",
			from: ExecutionStateTimeout,
			to:   ExecutionStateRunning,
			want: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := tt.from.CanTransitionTo(tt.to)

			if got != tt.want {
				t.Fatalf(
					"CanTransitionTo(%q) = %v, want %v",
					tt.to,
					got,
					tt.want,
				)
			}
		})
	}
}

func TestExecutionStateValidateTransitionTo(t *testing.T) {
	t.Run("valid transition", func(t *testing.T) {
		err := ExecutionStateRequested.ValidateTransitionTo(
			ExecutionStateRunning,
		)

		if err != nil {
			t.Fatalf("expected no error, got %v", err)
		}
	})

	t.Run("invalid transition", func(t *testing.T) {
		err := ExecutionStateRequested.ValidateTransitionTo(
			ExecutionStateCompleted,
		)

		if err == nil {
			t.Fatal("expected error for invalid transition")
		}
	})
}

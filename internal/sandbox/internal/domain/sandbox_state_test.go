package domain

import "testing"

func TestSandboxStateCanTransitionTo(t *testing.T) {
	tests := []struct {
		name string
		from SandboxState
		to   SandboxState
		want bool
	}{
		{
			name: "requested to creating",
			from: SandboxStateRequested,
			to:   SandboxStateCreating,
			want: true,
		},
		{
			name: "creating to ready",
			from: SandboxStateCreating,
			to:   SandboxStateReady,
			want: true,
		},
		{
			name: "creating to failed",
			from: SandboxStateCreating,
			to:   SandboxStateFailed,
			want: true,
		},
		{
			name: "ready to stopping",
			from: SandboxStateReady,
			to:   SandboxStateStopping,
			want: true,
		},
		{
			name: "stopping to stopped",
			from: SandboxStateStopping,
			to:   SandboxStateStopped,
			want: true,
		},
		{
			name: "stopped to deleted",
			from: SandboxStateStopped,
			to:   SandboxStateDeleted,
			want: true,
		},
		{
			name: "requested cannot skip creating",
			from: SandboxStateRequested,
			to:   SandboxStateReady,
			want: false,
		},
		{
			name: "ready cannot become failed directly",
			from: SandboxStateReady,
			to:   SandboxStateFailed,
			want: false,
		},
		{
			name: "ready cannot become deleted directly",
			from: SandboxStateReady,
			to:   SandboxStateDeleted,
			want: false,
		},
		{
			name: "stopped cannot go back to ready",
			from: SandboxStateStopped,
			to:   SandboxStateReady,
			want: false,
		},
		{
			name: "failed cannot transition",
			from: SandboxStateFailed,
			to:   SandboxStateReady,
			want: false,
		},
		{
			name: "deleted cannot transition",
			from: SandboxStateDeleted,
			to:   SandboxStateReady,
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

func TestSandboxStateValidateTransitionTo(t *testing.T) {
	t.Run("valid transition", func(t *testing.T) {
		err := SandboxStateRequested.ValidateTransitionTo(
			SandboxStateCreating,
		)

		if err != nil {
			t.Fatalf("expected no error, got %v", err)
		}
	})

	t.Run("invalid transition", func(t *testing.T) {
		err := SandboxStateRequested.ValidateTransitionTo(
			SandboxStateReady,
		)

		if err == nil {
			t.Fatal("expected error for invalid transition")
		}
	})
}

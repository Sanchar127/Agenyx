package domain

import (
	"testing"
	"time"

	"github.com/google/uuid"
)

func TestNewSandbox(t *testing.T) {
	metadata := map[string]string{
		"agent_id": "agent-123",
		"purpose":  "code-execution",
	}

	before := time.Now().UTC()
	sandbox := NewSandbox(metadata)
	after := time.Now().UTC()

	if sandbox == nil {
		t.Fatal("NewSandbox() returned nil")
	}

	if sandbox.State != SandboxStateRequested {
		t.Fatalf(
			"expected initial state %q, got %q",
			SandboxStateRequested,
			sandbox.State,
		)
	}

	if sandbox.ID == "" {
		t.Fatal("sandbox ID should not be empty")
	}

	if _, err := uuid.Parse(string(sandbox.ID)); err != nil {
		t.Fatalf("sandbox ID should be a valid UUID: %v", err)
	}

	if sandbox.CreatedAt.Before(before) || sandbox.CreatedAt.After(after) {
		t.Fatalf("CreatedAt is outside expected range: %v", sandbox.CreatedAt)
	}

	if sandbox.UpdatedAt.Before(before) || sandbox.UpdatedAt.After(after) {
		t.Fatalf("UpdatedAt is outside expected range: %v", sandbox.UpdatedAt)
	}

	if !sandbox.CreatedAt.Equal(sandbox.UpdatedAt) {
		t.Fatal("CreatedAt and UpdatedAt should initially be equal")
	}

	if len(sandbox.Metadata) != len(metadata) {
		t.Fatalf(
			"expected %d metadata entries, got %d",
			len(metadata),
			len(sandbox.Metadata),
		)
	}

	for key, expected := range metadata {
		if actual := sandbox.Metadata[key]; actual != expected {
			t.Fatalf(
				"metadata[%q] = %q, expected %q",
				key,
				actual,
				expected,
			)
		}
	}
}

func TestNewSandboxGeneratesUniqueIDs(t *testing.T) {
	first := NewSandbox(nil)
	second := NewSandbox(nil)

	if first.ID == second.ID {
		t.Fatal("two sandboxes should not have the same ID")
	}
}

func TestNewSandboxWithNilMetadata(t *testing.T) {
	sandbox := NewSandbox(nil)

	if sandbox == nil {
		t.Fatal("NewSandbox() returned nil")
	}

	if sandbox.Metadata != nil {
		t.Fatal("expected metadata to remain nil")
	}
}

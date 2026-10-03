package domain

import "testing"

func TestFilesystemPolicyValidate(t *testing.T) {
	policy := FilesystemPolicy{
		Mounts: []FilesystemMount{
			{
				Path:   "/workspace",
				Access: FilesystemAccessReadWrite,
			},
			{
				Path:   "/etc",
				Access: FilesystemAccessReadOnly,
			},
			{
				Path:   "/tmp",
				Access: FilesystemAccessReadWrite,
			},
		},
	}

	if err := policy.Validate(); err != nil {
		t.Fatalf("expected valid filesystem policy, got error: %v", err)
	}
}

func TestFilesystemPolicyValidateRejectsInvalidPolicies(t *testing.T) {
	tests := []struct {
		name   string
		policy FilesystemPolicy
	}{
		{
			name: "empty path",
			policy: FilesystemPolicy{
				Mounts: []FilesystemMount{
					{
						Path:   "",
						Access: FilesystemAccessReadWrite,
					},
				},
			},
		},
		{
			name: "relative path",
			policy: FilesystemPolicy{
				Mounts: []FilesystemMount{
					{
						Path:   "workspace",
						Access: FilesystemAccessReadWrite,
					},
				},
			},
		},
		{
			name: "invalid access",
			policy: FilesystemPolicy{
				Mounts: []FilesystemMount{
					{
						Path:   "/workspace",
						Access: FilesystemAccess("INVALID"),
					},
				},
			},
		},
		{
			name: "duplicate path",
			policy: FilesystemPolicy{
				Mounts: []FilesystemMount{
					{
						Path:   "/workspace",
						Access: FilesystemAccessReadWrite,
					},
					{
						Path:   "/workspace",
						Access: FilesystemAccessReadOnly,
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if err := tt.policy.Validate(); err == nil {
				t.Fatal("expected validation error, got nil")
			}
		})
	}
}

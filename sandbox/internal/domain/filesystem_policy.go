package domain

import (
	"fmt"
	"path/filepath"
)

type FilesystemAccess string

const (
	FilesystemAccessReadOnly  FilesystemAccess = "READ_ONLY"
	FilesystemAccessReadWrite FilesystemAccess = "READ_WRITE"
	FilesystemAccessNone      FilesystemAccess = "NONE"
)

type FilesystemMount struct {
	Path   string
	Access FilesystemAccess
}

type FilesystemPolicy struct {
	Mounts []FilesystemMount
}

func (p FilesystemPolicy) Validate() error {
	seen := make(map[string]struct{}, len(p.Mounts))

	for _, mount := range p.Mounts {
		if mount.Path == "" {
			return fmt.Errorf("%w: filesystem path cannot be empty", ErrInvalidInput)
		}

		if !filepath.IsAbs(mount.Path) {
			return fmt.Errorf(
				"%w: filesystem path must be absolute: %q",
				ErrInvalidInput,
				mount.Path,
			)
		}

		switch mount.Access {
		case FilesystemAccessReadOnly,
			FilesystemAccessReadWrite,
			FilesystemAccessNone:
		default:
			return fmt.Errorf(
				"%w: invalid filesystem access %q for path %q",
				ErrInvalidInput,
				mount.Access,
				mount.Path,
			)
		}

		if _, exists := seen[mount.Path]; exists {
			return fmt.Errorf(
				"%w: duplicate filesystem path: %q",
				ErrInvalidInput,
				mount.Path,
			)
		}

		seen[mount.Path] = struct{}{}
	}

	return nil
}

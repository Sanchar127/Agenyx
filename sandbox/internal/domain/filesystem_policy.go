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
			return fmt.Errorf("filesystem path cannot be empty")
		}

		if !filepath.IsAbs(mount.Path) {
			return fmt.Errorf(
				"filesystem path must be absolute: %q",
				mount.Path,
			)
		}

		switch mount.Access {
		case FilesystemAccessReadOnly,
			FilesystemAccessReadWrite,
			FilesystemAccessNone:
		default:
			return fmt.Errorf(
				"invalid filesystem access %q for path %q",
				mount.Access,
				mount.Path,
			)
		}

		if _, exists := seen[mount.Path]; exists {
			return fmt.Errorf(
				"duplicate filesystem path: %q",
				mount.Path,
			)
		}

		seen[mount.Path] = struct{}{}
	}

	return nil
}

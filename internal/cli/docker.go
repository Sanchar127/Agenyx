package cli

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

type Project struct {
	Root string
}

func FindProjectRoot() (*Project, error) {
	dir, err := os.Getwd()
	if err != nil {
		return nil, err
	}

	for {
		compose := filepath.Join(dir, "docker-compose.yml")

		if _, err := os.Stat(compose); err == nil {
			return &Project{Root: dir}, nil
		}

		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}

		dir = parent
	}

	return nil, fmt.Errorf("could not locate docker-compose.yml")
}

func (p *Project) Compose(args ...string) *exec.Cmd {
	baseArgs := []string{
		"compose",
		"--project-directory", p.Root,
		"-f", filepath.Join(p.Root, "docker-compose.yml"),
	}

	if _, err := os.Stat(filepath.Join(p.Root, ".env")); err == nil {
		baseArgs = append(baseArgs,
			"--env-file", filepath.Join(p.Root, ".env"),
		)
	}

	baseArgs = append(baseArgs, args...)

	cmd := exec.Command("docker", baseArgs...)
	cmd.Dir = p.Root

	return cmd
}

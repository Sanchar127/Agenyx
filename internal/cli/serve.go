package cli

import (
	"fmt"
	"os/exec"

	"github.com/spf13/cobra"
)

var serveCmd = &cobra.Command{
	Use:   "serve",
	Short: "Build and deploy the entire Agenyx platform",
	RunE:  runServe,
}

func runServe(cmd *cobra.Command, args []string) error {
	PrintBanner()

	fmt.Println("  Initializing deployment...")
	fmt.Println()

	if _, err := exec.LookPath("docker"); err != nil {
		return fmt.Errorf("Docker CLI is not installed")
	}

	Success("Docker CLI detected")

	project, err := FindProjectRoot()
	if err != nil {
		return err
	}

	Success("Project root: " + project.Root)

	if err := runComposeStep(
		project,
		"Validating Docker Compose configuration",
		"config", "--quiet",
	); err != nil {
		return err
	}

	if err := runComposeStep(
		project,
		"Building and starting all Agenyx containers",
		"up",
		"--build",
		"--detach",
		"--remove-orphans",
		"--wait",
		"--wait-timeout", "300",
	); err != nil {
		return fmt.Errorf("deployment failed: %w", err)
	}

	fmt.Println()
	PrintDeploymentSummary()

	return nil
}

func runComposeStep(project *Project, message string, args ...string) error {
	var output []byte

	err := WithSpinner(message, func() error {
		var commandErr error
		output, commandErr = project.Compose(args...).CombinedOutput()
		return commandErr
	})

	if len(output) > 0 {
		fmt.Println(string(output))
	}

	return err
}

func PrintDeploymentSummary() {
	fmt.Println("  ┌─────────────────────────────────────────┐")
	fmt.Println("  │           AGENYX IS RUNNING             │")
	fmt.Println("  │                                         │")
	fmt.Println("  │  Gateway:     https://localhost:8443    │")
	fmt.Println("  │  Agent:       http://localhost:8000     │")
	fmt.Println("  │  Inference:   http://localhost:8004     │")
	fmt.Println("  │  Router:      http://localhost:8005     │")
	fmt.Println("  │                                         │")
	fmt.Println("  └─────────────────────────────────────────┘")
}

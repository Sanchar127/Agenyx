package cli

import (
	"fmt"

	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:           "agenyx",
	Short:         "Agenyx AI Agent Orchestration Platform",
	SilenceUsage:  true,
	SilenceErrors: true,
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.AddCommand(serveCmd)

	rootCmd.AddCommand(&cobra.Command{
		Use:   "version",
		Short: "Display Agenyx version",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Println("Agenyx CLI v0.1.0")
		},
	})
}

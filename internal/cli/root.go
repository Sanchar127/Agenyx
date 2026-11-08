package cli

import (
	"fmt"
	"log/slog"
	"os"

	"github.com/sanchar127/agenyx/internal/eval"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:           "agenyx",
	Short:         "Agenyx AI Agent Orchestration Platform",
	SilenceUsage:  true,
	SilenceErrors: true,
}

var evalAPICmd = &cobra.Command{
	Use:   "eval-api",
	Short: "Start the evaluation API server",
	RunE:  runEvalAPI,
}

var evalSchedulerCmd = &cobra.Command{
	Use:   "eval-scheduler",
	Short: "Start the evaluation scheduler",
	RunE:  runEvalScheduler,
}

func Execute() error {
	return rootCmd.Execute()
}

func init() {
	rootCmd.AddCommand(serveCmd)
	rootCmd.AddCommand(evalAPICmd)
	rootCmd.AddCommand(evalSchedulerCmd)

	rootCmd.AddCommand(&cobra.Command{
		Use:   "version",
		Short: "Display Agenyx version",
		Run: func(cmd *cobra.Command, args []string) {
			fmt.Println("Agenyx CLI v0.1.0")
		},
	})
}

func runEvalAPI(cmd *cobra.Command, args []string) error {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := eval.Config{
		APIAddr:             getEnv("EVAL_API_ADDR", ":8006"),
		DatabaseURL:         getEnv("EVAL_DATABASE_URL", ""),
		ValkeyURL:           getEnv("EVAL_VALKEY_URL", "redis://valkey:6379/0"),
		ValkeyStream:        getEnv("EVAL_VALKEY_STREAM", "eval:jobs"),
		ValkeyConsumerGroup: getEnv("EVAL_VALKEY_CONSUMER_GROUP", "eval-workers"),
		LogLevel:            getEnv("EVAL_LOG_LEVEL", "info"),
		LogJSON:             getEnv("EVAL_LOG_JSON", "true") == "true",
	}

	store := eval.NewMockStore()
	return eval.Run(cfg, store, logger)
}

func runEvalScheduler(cmd *cobra.Command, args []string) error {
	logger := slog.New(slog.NewTextHandler(os.Stdout, nil))
	cfg := eval.Config{
		SchedulerAddr:       getEnv("EVAL_SCHEDULER_ADDR", ":8007"),
		DatabaseURL:         getEnv("EVAL_DATABASE_URL", ""),
		ValkeyURL:           getEnv("EVAL_VALKEY_URL", "redis://valkey:6379/0"),
		ValkeyStream:        getEnv("EVAL_VALKEY_STREAM", "eval:jobs"),
		ValkeyConsumerGroup: getEnv("EVAL_VALKEY_CONSUMER_GROUP", "eval-workers"),
		JobLeaseSeconds:     300,
		MaxJobAttempts:      3,
		LogLevel:            getEnv("EVAL_LOG_LEVEL", "info"),
		LogJSON:             getEnv("EVAL_LOG_JSON", "true") == "true",
	}

	store := eval.NewMockStore()
	return eval.Run(cfg, store, logger)
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

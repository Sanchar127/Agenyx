package main

import (
	"os"

	"github.com/sanchar127/agenyx/internal/cli"
)

func main() {
	if err := cli.Execute(); err != nil {
		os.Exit(1)
	}
}

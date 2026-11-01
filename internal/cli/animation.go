package cli

import (
	"fmt"
	"time"

	"github.com/charmbracelet/lipgloss"
)

var spinnerStyle = lipgloss.NewStyle().
	Foreground(lipgloss.Color("#7C5CFC"))

func WithSpinner(message string, operation func() error) error {
	frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}

	done := make(chan struct{})
	stopped := make(chan struct{})

	go func() {
		defer close(stopped)

		ticker := time.NewTicker(100 * time.Millisecond)
		defer ticker.Stop()

		i := 0

		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				fmt.Printf("\r  %s %s",
					spinnerStyle.Render(frames[i%len(frames)]),
					message,
				)
				i++
			}
		}
	}()

	err := operation()

	close(done)
	<-stopped

	fmt.Print("\r\033[2K")

	if err != nil {
		fmt.Printf("  ✗ %s\n", message)
		return err
	}

	Success(message)
	return nil
}

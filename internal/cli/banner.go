package cli

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
)

var (
	logoStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#7C5CFC"))

	subtitleStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("#A0A0A0"))

	successStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("#00D787"))
)

func PrintBanner() {
	logo := `
   _                    _
  / \   __ _  ___ _ __ | |__  __  __
 / _ \ / _` + "`" + ` |/ _ \ '_ \| '_ \ \ \/ /
/ ___ \ (_| |  __/ | | | |_) | >  <
/_/   \_\__, |\___|_| |_|_.__/ /_/\_\
        |___/
`

	fmt.Println(logoStyle.Render(logo))
	fmt.Println(subtitleStyle.Render("       AI AGENT ORCHESTRATION PLATFORM"))
	fmt.Println()
}

func Success(message string) {
	fmt.Println(successStyle.Render("  ✓ " + message))
}

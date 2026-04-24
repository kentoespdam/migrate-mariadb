package tui

import (
	"fmt"

	tea "charm.land/bubbletea/v2"
)

// Phase merepresentasikan tahapan aktif dalam aplikasi TUI.
type Phase int

const (
	PhaseLoading Phase = iota
	PhaseDashboard
	PhaseMapping
	PhaseConfig
	PhaseMonitor
	PhaseSummary
)

// Model adalah top-level state machine untuk MariaSync-Go TUI.
type Model struct {
	phase  Phase
	err    error
	width  int
	height int

	// Sub-models untuk setiap fase
	dashboard dashboardModel
	mapping   mappingModel
	config    configModel
	monitor   monitorModel
}

// NewModel membuat instance baru dari top-level TUI model.
func NewModel() Model {
	return Model{
		phase:     PhaseLoading,
		dashboard: newDashboardModel(),
		mapping:   newMappingModel(),
		config:    newConfigModel(),
		monitor:   newMonitorModel(),
	}
}

func (m Model) Init() tea.Cmd {
	// Inisialisasi awal (misal: start discovery) akan ditambahkan di sini.
	return nil
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd

	// Global key handling
	if kmsg, ok := msg.(tea.KeyMsg); ok {
		switch kmsg.String() {
		case "ctrl+c":
			return m, tea.Quit
		}
	}

	// Handle window resizing globally
	if wmsg, ok := msg.(tea.WindowSizeMsg); ok {
		m.width = wmsg.Width
		m.height = wmsg.Height
		// Teruskan resize ke semua sub-models jika perlu
	}

	// Delegasi Update berdasarkan Phase
	switch m.phase {
	case PhaseDashboard:
		m.dashboard, cmd = m.dashboard.Update(msg)
		// Check if dashboard wants to transition
		if m.dashboard.done {
			m.phase = PhaseMapping
			// Pass data to next phase?
		}
		// Case lainnya menyusul
	}

	return m, cmd
}

func (m Model) View() tea.View {
	if m.err != nil {
		return tea.NewView(fmt.Sprintf("Error: %v\n\nTekan ctrl+c untuk keluar.", m.err))
	}

	switch m.phase {
	case PhaseLoading:
		return tea.NewView("\n  Memuat data... Mohon tunggu.")
	case PhaseDashboard:
		return m.dashboard.View()
	case PhaseMapping:
		return m.mapping.View()
	case PhaseConfig:
		return m.config.View()
	case PhaseMonitor:
		return m.monitor.View()
	case PhaseSummary:
		return tea.NewView("\n  Migrasi Selesai!")
	default:
		return tea.NewView("Fase tidak dikenal")
	}
}

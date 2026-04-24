package tui

import (
	tea "charm.land/bubbletea/v2"
)

type monitorModel struct {
	done bool
}

func newMonitorModel() monitorModel {
	return monitorModel{}
}

func (m monitorModel) Update(msg tea.Msg) (monitorModel, tea.Cmd) {
	return m, nil
}

func (m monitorModel) View() tea.View {
	return tea.NewView("\n  Fase Monitoring (Sedang dikerjakan...)\n  q: berhenti.")
}

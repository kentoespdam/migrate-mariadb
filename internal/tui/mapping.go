package tui

import (
	tea "charm.land/bubbletea/v2"
)

type mappingModel struct {
	done bool
}

func newMappingModel() mappingModel {
	return mappingModel{}
}

func (m mappingModel) Update(msg tea.Msg) (mappingModel, tea.Cmd) {
	return m, nil
}

func (m mappingModel) View() tea.View {
	return tea.NewView("\n  Fase Mapping (Sedang dikerjakan...)\n  Tekan 'n' untuk lanjut ke Config.")
}

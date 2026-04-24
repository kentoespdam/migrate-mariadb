package tui

import (
	tea "charm.land/bubbletea/v2"
)

type configModel struct {
	done bool
}

func newConfigModel() configModel {
	return configModel{}
}

func (m configModel) Update(msg tea.Msg) (configModel, tea.Cmd) {
	return m, nil
}

func (m configModel) View() tea.View {
	return tea.NewView("\n  Fase Konfigurasi (Sedang dikerjakan...)\n  Tekan 'Enter' untuk mulai migrasi.")
}

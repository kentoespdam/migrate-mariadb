package tui

import (
	"fmt"
	"io"

	"mariasyncgo/internal/discovery"

	"charm.land/bubbles/v2/list"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
)

// tableItem merepresentasikan baris tabel dalam list dashboard.
type tableItem struct {
	table    discovery.Table
	selected bool
	eligible bool // false jika tabel hanya ada di satu sisi atau tidak kompatibel
	status   string
}

func (i tableItem) FilterValue() string { return i.table.Name }

// tableDelegate merender item tabel dalam list.
type tableDelegate struct{}

func (d tableDelegate) Height() int                             { return 1 }
func (d tableDelegate) Spacing() int                            { return 0 }
func (d tableDelegate) Update(_ tea.Msg, _ *list.Model) tea.Cmd { return nil }
func (d tableDelegate) Render(w io.Writer, m list.Model, index int, listItem list.Item) {
	it, ok := listItem.(tableItem)
	if !ok {
		return
	}

	style := lipgloss.NewStyle().PaddingLeft(2)
	checkbox := "[ ]"
	if it.selected {
		checkbox = "[x]"
	}

	if !it.eligible {
		checkbox = "⛔"
		style = style.Foreground(lipgloss.Color("240")) // Greyed out
	}

	if index == m.Index() {
		style = style.Foreground(lipgloss.Color("170")).Bold(true)
	}

	str := fmt.Sprintf("%s %-20s %10d rows   %s", checkbox, it.table.Name, it.table.RowCount, it.status)
	fmt.Fprint(w, style.Render(str))
}

type dashboardModel struct {
	list     list.Model
	items    []tableItem
	done     bool
	quitting bool
}

func newDashboardModel() dashboardModel {
	// Dummy items untuk pengembangan awal UI
	items := []list.Item{
		tableItem{table: discovery.Table{Name: "users", RowCount: 1200000}, selected: true, eligible: true, status: "✓ skema cocok"},
		tableItem{table: discovery.Table{Name: "orders", RowCount: 89000}, eligible: true, status: "⚠ 2 kolom beda tipe"},
		tableItem{table: discovery.Table{Name: "products", RowCount: 15400}, selected: true, eligible: true, status: "✓ skema cocok"},
		tableItem{table: discovery.Table{Name: "_logs", RowCount: 0}, eligible: false, status: "⛔ hanya di source"},
	}

	l := list.New(items, tableDelegate{}, 0, 0)
	l.Title = "MariaSync-Go · Pilih Tabel untuk Migrasi"
	l.SetShowStatusBar(false)
	l.SetFilteringEnabled(true)

	return dashboardModel{
		list:  l,
		items: make([]tableItem, 0), // Akan diisi dari discovery
	}
}

func (m dashboardModel) Update(msg tea.Msg) (dashboardModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		switch msg.String() {
		case "space":
			if it, ok := m.list.SelectedItem().(tableItem); ok && it.eligible {
				// Toggle selection logic
				idx := m.list.Index()
				// Kita perlu update di slice items asli and di list.Item
				it.selected = !it.selected
				m.list.SetItem(idx, it)
			}
			return m, nil
		case "a":
			// Select all eligible logic
			for i, item := range m.list.Items() {
				if it, ok := item.(tableItem); ok && it.eligible {
					it.selected = true
					m.list.SetItem(i, it)
				}
			}
			return m, nil
		case "enter":
			// Validasi minimal 1 terpilih
			anySelected := false
			for _, item := range m.list.Items() {
				if it, ok := item.(tableItem); ok && it.selected {
					anySelected = true
					break
				}
			}
			if anySelected {
				m.done = true
			}
			return m, nil
		}
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m dashboardModel) View() tea.View {
	return tea.NewView(fmt.Sprintf("\n%s\n Space: pilih  ·  a: pilih semua  ·  Enter: lanjut  ·  q/ctrl+c: keluar", m.list.View()))
}

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select

from ...db.metadata import ColumnInfo


class MappingModal(ModalScreen[Optional[dict[str, str | None]]]):
    """Modal for custom column mapping."""

    def __init__(self, table_name: str, source_cols: list[ColumnInfo], target_cols: list[ColumnInfo], current_mapping: dict[str, str | None] | None = None):
        super().__init__()
        self.table_name = table_name
        self.source_cols = source_cols
        self.target_cols = target_cols
        self.mapping = current_mapping or {col.name: col.name if any(tc.name == col.name for tc in target_cols) else None for col in source_cols}

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Label(f"Column Mapping: {self.table_name}", id="modal-title")

            with ScrollableContainer():
                for col in self.source_cols:
                    with Horizontal(classes="mapping-row"):
                        label_text = f"{col.name} ({col.data_type})"
                        if col.is_pk:
                            label_text = "🔑 " + label_text

                        yield Label(label_text, classes="column-name")
                        yield Label("──▶", classes="arrow")

                        options = [(tc.name, tc.name) for tc in self.target_cols]
                        if not col.is_pk:
                            options.insert(0, ("— Skip —", None))

                        initial_value = self.mapping.get(col.name)
                        if initial_value not in [o[1] for o in options]:
                            initial_value = None

                        yield Select(
                            options,
                            value=initial_value,
                            id=f"select-{col.name}",
                            classes="target-select",
                            allow_blank=True if not col.is_pk else False
                        )

            yield Label("⚠️ Primary Key columns must be mapped", id="pk-warning", classes="confirm-warning")

            with Horizontal(classes="modal-buttons"):
                yield Button("Cancel", id="cancel-btn")
                yield Button("Save Mapping", variant="success", id="save-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
        elif event.button.id == "save-btn":
            # Reconstruct mapping from selects
            final_mapping = {}
            for col in self.source_cols:
                select = self.query_one(f"#select-{col.name}", Select)
                final_mapping[col.name] = select.value

            self.dismiss(final_mapping)

    def on_mount(self) -> None:
        self.check_pk_mapping()

    def on_select_changed(self, event: Select.Changed) -> None:
        self.check_pk_mapping()

    def check_pk_mapping(self) -> None:
        """Ensure all PKs are mapped."""
        all_pk_mapped = True
        for col in self.source_cols:
            if col.is_pk:
                select = self.query_one(f"#select-{col.name}", Select)
                if select.value is None:
                    all_pk_mapped = False
                    break

        self.query_one("#save-btn", Button).disabled = not all_pk_mapped
        self.query_one("#pk-warning", Label).visible = not all_pk_mapped

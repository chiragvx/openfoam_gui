from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QDialogButtonBox, QFormLayout
)
from core.settings_manager import SettingsManager
from gui.theme_manager import ThemeManager

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setFixedWidth(350)
        
        self.layout = QVBoxLayout(self)
        self.form = QFormLayout()
        
        # Theme
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        current_theme = SettingsManager.get("theme")
        self.theme_combo.setCurrentText(current_theme)
        self.form.addRow("Theme:", self.theme_combo)
        
        # Units
        self.units_combo = QComboBox()
        self.units_combo.addItems(["m", "cm", "mm", "in", "ft"])
        current_units = SettingsManager.get("units")
        self.units_combo.setCurrentText(current_units)
        self.form.addRow("Length Units:", self.units_combo)
        
        self.layout.addLayout(self.form)
        
        # Buttons
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

    def _on_accept(self):
        theme = self.theme_combo.currentText()
        units = self.units_combo.currentText()
        
        SettingsManager.set("theme", theme)
        SettingsManager.set("units", units)
        
        ThemeManager.apply_theme(theme)
        self.accept()

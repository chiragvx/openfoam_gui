from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
    QTextEdit, QListWidget, QGroupBox, QFormLayout, QDialogButtonBox,
    QFrame
)
from PyQt6.QtCore import Qt
from core.study_manager import StudyManager, Study

class StudyStartupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Get Started")
        self.setFixedSize(300, 200)
        self.chosen = "skip"
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        lbl = QLabel("Welcome to OpenFOAM RC CFD\nWould you like to start a new study or load an existing one?")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        
        btn_new = QPushButton("New Study")
        btn_new.setFixedHeight(40)
        btn_new.clicked.connect(self._on_new)
        layout.addWidget(btn_new)
        
        btn_load = QPushButton("Load Study")
        btn_load.setFixedHeight(40)
        btn_load.clicked.connect(self._on_load)
        layout.addWidget(btn_load)
        
        btn_skip = QPushButton("Skip (Anonymous Run)")
        btn_skip.setFlat(True)
        btn_skip.clicked.connect(self._on_skip)
        layout.addWidget(btn_skip)

    def _on_new(self):
        self.chosen = "new"
        self.accept()

    def _on_load(self):
        self.chosen = "load"
        self.accept()

    def _on_skip(self):
        self.chosen = "skip"
        self.accept()

class NewStudyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Study")
        self.setFixedWidth(400)
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Wing at 20 m/s")
        self._name.textChanged.connect(self._validate)
        
        self._desc = QTextEdit()
        self._desc.setMaximumHeight(80)
        self._desc.setPlaceholderText("Optional description...")
        
        form.addRow("Study Name:", self._name)
        form.addRow("Description:", self._desc)
        layout.addLayout(form)
        
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        layout.addWidget(self.buttons)

    def _validate(self):
        name = self._name.text().strip()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(len(name) > 0)

    @property
    def name(self):
        return self._name.text().strip()

    @property
    def description(self):
        return self._desc.toPlainText().strip()

class LoadStudyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load Study")
        self.resize(600, 400)
        self.selected_study = None
        
        layout = QHBoxLayout(self)
        
        # Left side: List
        left_layout = QVBoxLayout()
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self.accept)
        left_layout.addWidget(QLabel("Recent Studies:"))
        left_layout.addWidget(self._list)
        
        layout.addLayout(left_layout, 2)
        
        # Right side: Preview
        right_layout = QVBoxLayout()
        preview_box = QGroupBox("Study Preview")
        preview_form = QFormLayout(preview_box)
        
        self._lbl_name = QLabel("-")
        self._lbl_date = QLabel("-")
        self._lbl_speed = QLabel("-")
        self._lbl_aoa = QLabel("-")
        self._lbl_solved = QLabel("-")
        
        preview_form.addRow("Name:", self._lbl_name)
        preview_form.addRow("Created:", self._lbl_date)
        preview_form.addRow("Airspeed:", self._lbl_speed)
        preview_form.addRow("AoA:", self._lbl_aoa)
        preview_form.addRow("Status:", self._lbl_solved)
        
        right_layout.addWidget(preview_box)
        right_layout.addStretch()
        
        btn_layout = QHBoxLayout()
        self._btn_delete = QPushButton("Delete")
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_delete.setEnabled(False)
        
        self._btn_load = QPushButton("Load")
        self._btn_load.clicked.connect(self.accept)
        self._btn_load.setEnabled(False)
        self._btn_load.setDefault(True)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(self._btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self._btn_load)
        
        right_layout.addLayout(btn_layout)
        layout.addLayout(right_layout, 3)
        
        self._studies = []
        self._refresh_list()

    def _refresh_list(self):
        self._list.clear()
        self._studies = StudyManager.list_studies()
        for s in self._studies:
            solved_badge = " ✓" if s.results.get("solved") else ""
            self._list.addItem(f"{s.name} ({s.created[:10]}){solved_badge}")
        
    def _on_selection_changed(self):
        idx = self._list.currentRow()
        if idx < 0:
            self.selected_study = None
            self._btn_load.setEnabled(False)
            self._btn_delete.setEnabled(False)
            self._lbl_name.setText("-")
            return
            
        s = self._studies[idx]
        self.selected_study = s
        self._btn_load.setEnabled(True)
        self._btn_delete.setEnabled(True)
        
        self._lbl_name.setText(s.name)
        self._lbl_date.setText(s.created[:16].replace("T", " "))
        
        cond = s.conditions
        self._lbl_speed.setText(f"{cond.get('airspeed', '-')} m/s")
        self._lbl_aoa.setText(f"{cond.get('aoa_deg', '-')}°")
        
        solved = s.results.get("solved", False)
        self._lbl_solved.setText("SOLVED" if solved else "Incomplete")
        self._lbl_solved.setStyleSheet("color: green" if solved else "color: orange")

    def _on_delete(self):
        if self.selected_study:
            StudyManager.delete(self.selected_study.study_id)
            self._refresh_list()

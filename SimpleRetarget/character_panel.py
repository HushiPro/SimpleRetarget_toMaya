"""
CharacterPanel — left or right column showing a character's hierarchy
as an interactive hypergraph with bone / curve toggle.
"""
import maya.cmds as cmds

from .compat import QtCore, QtWidgets
from .hypergraph_widget import HypergraphWidget


class CharacterPanel(QtWidgets.QWidget):
    """Load a character root and visualise its hierarchy."""

    def __init__(self, title, parent=None):
        super(CharacterPanel, self).__init__(parent)
        self.root_node = None

        # title
        title_label = QtWidgets.QLabel(title)
        title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #ccc;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)

        # character selector
        self.root_field = QtWidgets.QLineEdit()
        self.root_field.setPlaceholderText("Select root node...")
        self.root_field.setReadOnly(True)

        self.load_btn = QtWidgets.QPushButton("Load Selected")
        self.load_btn.setToolTip(
            "Select the root joint or group in Maya, then click Load")

        selector_layout = QtWidgets.QHBoxLayout()
        selector_layout.addWidget(self.root_field)
        selector_layout.addWidget(self.load_btn)

        # display-mode toggle
        self.mode_group = QtWidgets.QButtonGroup(self)
        self.bone_radio = QtWidgets.QRadioButton("Bones")
        self.curve_radio = QtWidgets.QRadioButton("Curves")
        self.bone_radio.setChecked(True)
        self.mode_group.addButton(self.bone_radio)
        self.mode_group.addButton(self.curve_radio)

        mode_layout = QtWidgets.QHBoxLayout()
        mode_layout.addWidget(self.bone_radio)
        mode_layout.addWidget(self.curve_radio)
        mode_layout.addStretch()

        # hypergraph
        self.hypergraph = HypergraphWidget()

        # assemble
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title_label)
        layout.addLayout(selector_layout)
        layout.addLayout(mode_layout)
        layout.addWidget(self.hypergraph)

        # connections
        self.load_btn.clicked.connect(self._load_character)
        self.bone_radio.toggled.connect(self._on_mode_changed)
        self.curve_radio.toggled.connect(self._on_mode_changed)

    # --------------------------------------------------------

    def _load_character(self):
        sel = cmds.ls(selection=True)
        if not sel:
            cmds.warning("Select a root node first!")
            return
        self.root_node = sel[0]
        self.root_field.setText(self.root_node)
        self._rebuild_graph()

    def _on_mode_changed(self):
        if self.root_node:
            self._rebuild_graph()

    def _rebuild_graph(self):
        mode = 'bone' if self.bone_radio.isChecked() else 'curve'
        self.hypergraph.build_graph(self.root_node, mode)

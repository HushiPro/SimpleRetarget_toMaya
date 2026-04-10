"""
Main retargeting tool dialog — three-column layout with source hypergraph,
matching panel, and target hypergraph.
"""
from functools import partial

import maya.cmds as cmds

from .compat import QtCore, QtWidgets, maya_main_window
from .constants import MAYA_COLOR_INDEX, MAIN_STYLESHEET
from . import core
from .character_panel import CharacterPanel
from .matching_panel import MatchingPanel
from .batch_export import BatchExport
from .constraint_manager import ConstraintManager


class RetargetingTool(QtWidgets.QDialog):
    """Main application window."""

    WINDOW_TITLE = "Animation Retargeting Tool"

    def __init__(self):
        super(RetargetingTool, self).__init__(maya_main_window())

        self.script_job_ids = []
        self.color_counter = 0
        self._batch_window = None
        self._constraint_window = None

        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowFlags(
            (self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
            | QtCore.Qt.WindowMinMaxButtonsHint)
        self.resize(1400, 800)
        self.setMinimumSize(900, 500)

        if cmds.about(macOS=True):
            self.setWindowFlags(
                QtCore.Qt.Tool | QtCore.Qt.WindowMinMaxButtonsHint)

        self._build_ui()
        self._build_connections()
        self._create_script_jobs()
        self.setStyleSheet(MAIN_STYLESHEET)

    # ============================================================ UI build

    def _build_ui(self):
        # --- three panels ---
        self.source_panel = CharacterPanel("Source Character")
        self.target_panel = CharacterPanel("Target Character")
        self.matching_panel = MatchingPanel(self)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.source_panel)
        splitter.addWidget(self.matching_panel)
        splitter.addWidget(self.target_panel)
        splitter.setSizes([400, 400, 400])
        splitter.setHandleWidth(3)

        # --- options bar ---
        self.rot_checkbox = QtWidgets.QCheckBox("Rotation")
        self.pos_checkbox = QtWidgets.QCheckBox("Translation")
        self.snap_checkbox = QtWidgets.QCheckBox("Align To Position")
        self.rot_checkbox.setChecked(True)
        self.pos_checkbox.setChecked(True)
        self.snap_checkbox.setChecked(True)

        options_layout = QtWidgets.QHBoxLayout()
        options_layout.addWidget(self.rot_checkbox)
        options_layout.addWidget(self.pos_checkbox)
        options_layout.addWidget(self.snap_checkbox)
        options_layout.addStretch()

        # --- action buttons ---
        self.apply_btn = QtWidgets.QPushButton("Refresh All Connections")
        self.apply_btn.setMinimumHeight(32)
        self.apply_btn.setStyleSheet(
            "background-color: #4a90d9; color: white; "
            "font-weight: bold; border-radius: 4px;")

        self.bake_btn = QtWidgets.QPushButton("Bake Animation")
        self.bake_btn.setMinimumHeight(32)
        self.bake_btn.setStyleSheet(
            "background-color: #5cb85c; color: white; "
            "font-weight: bold; border-radius: 4px;")

        self.batch_btn = QtWidgets.QPushButton("Batch Bake && Export...")
        self.batch_btn.setMinimumHeight(32)

        self.constraints_btn = QtWidgets.QPushButton("Manage Constraints")
        self.constraints_btn.setMinimumHeight(32)

        self.refresh_ikfk_btn = QtWidgets.QPushButton("Refresh IK/FK")
        self.refresh_ikfk_btn.setMinimumHeight(32)

        self.help_btn = QtWidgets.QPushButton("?")
        self.help_btn.setFixedSize(32, 32)

        buttons_layout = QtWidgets.QHBoxLayout()
        buttons_layout.addWidget(self.apply_btn)
        buttons_layout.addWidget(self.refresh_ikfk_btn)
        buttons_layout.addWidget(self.batch_btn)
        buttons_layout.addWidget(self.constraints_btn)
        buttons_layout.addWidget(self.bake_btn)
        buttons_layout.addWidget(self.help_btn)

        # --- separator ---
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)

        # --- main layout ---
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(splitter, 1)
        main_layout.addLayout(options_layout)
        main_layout.addWidget(separator)
        main_layout.addLayout(buttons_layout)

    def _build_connections(self):
        self.apply_btn.clicked.connect(self._refresh_all_connections)
        self.bake_btn.clicked.connect(self._bake_animation_confirm)
        self.batch_btn.clicked.connect(self._open_batch_window)
        self.constraints_btn.clicked.connect(self._open_constraint_window)
        self.help_btn.clicked.connect(self._help_dialog)
        self.refresh_ikfk_btn.clicked.connect(self._refresh_ik_fk)

    def _create_script_jobs(self):
        self.script_job_ids.append(
            cmds.scriptJob(
                event=["SelectionChanged",
                       partial(self._on_maya_selection_changed)]))

    def _on_maya_selection_changed(self):
        """Sync both hypergraphs when the user picks objects in the viewport."""
        self.source_panel.hypergraph.sync_selection_from_maya()
        self.target_panel.hypergraph.sync_selection_from_maya()

    # ============================================================ actions

    def _refresh_all_connections(self):
        """Remove existing connections, re-create from current mappings,
        and update the connected-state visuals on both hypergraphs."""
        core.remove_all_connections()

        mappings = self.matching_panel.get_all_mappings()

        color_keys = list(MAYA_COLOR_INDEX.keys())
        color_idx = color_keys[self.color_counter % len(color_keys)]
        do_rot = self.rot_checkbox.isChecked()
        do_tran = self.pos_checkbox.isChecked()
        snap = self.snap_checkbox.isChecked()

        connected_sources = set()
        connected_targets = set()

        for source, target, is_ik, rot_override, tran_override in mappings:
            if not cmds.objExists(source) or not cmds.objExists(target):
                cmds.warning(
                    "Node '{}' or '{}' does not exist — skipping.".format(
                        source, target))
                continue

            slot_rot = do_rot if rot_override is None else rot_override
            slot_tran = do_tran if tran_override is None else tran_override
            if not slot_rot and not slot_tran:
                cmds.warning(
                    "Both rotation and translation are disabled for '{}' — skipping.".format(
                        source))
                continue

            if is_ik:
                core.create_ik_connection(
                    source, target, snap, color_idx, slot_rot, slot_tran)
            else:
                core.create_connection(
                    source, target, slot_rot, slot_tran, snap, color_idx)
            connected_sources.add(source)
            connected_targets.add(target)

        self.matching_panel.mark_slots_connected(connected_sources)
        if self._constraint_window:
            self._constraint_window.refresh_constraints()

    def _bake_animation_confirm(self):
        result = cmds.confirmDialog(
            title="Confirm",
            message=("Baking the animation will delete all connection nodes. "
                     "Do you wish to proceed?"),
            button=["Yes", "No"],
            defaultButton="Yes",
            cancelButton="No",
        )
        if result != "Yes":
            return

        progress = QtWidgets.QProgressDialog(
            "Baking animation", None, 0, -1, self)
        progress.setWindowFlags(
            progress.windowFlags() ^ QtCore.Qt.WindowCloseButtonHint)
        progress.setWindowFlags(
            progress.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        progress.setWindowTitle("Progress...")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()
        QtCore.QCoreApplication.processEvents()

        core.bake_animation()
        progress.close()
        self.matching_panel.mark_slots_connected(set())
        if self._constraint_window:
            self._constraint_window.refresh_constraints()

    def _refresh_ik_fk(self):
        self.source_panel.hypergraph.refresh_ik_fk_states()
        self.target_panel.hypergraph.refresh_ik_fk_states()

    def _help_dialog(self):
        cmds.confirmDialog(
            title="How to Use",
            message=(
                "1. Load source character (skeleton / rig with animation) "
                "in the left panel.\n"
                "2. Load target character (rig to receive animation) "
                "in the right panel.\n"
                "3. Select nodes in the source graph, click "
                "'+ Add Slots from Source'.\n"
                "4. Select a node in the target graph, then click the "
                "right side of a slot to assign it.\n"
                "5. Right-click a slot to toggle IK mode or remove it.\n"
                "6. Click 'Refresh All Connections' to create/update constraints.\n"
                "   Connected nodes will show a green border.\n"
                "7. Click 'Bake Animation' when ready.\n\n"
                "Tips:\n"
                "  - Use 'Bones' / 'Curves' radio buttons to switch display.\n"
                "  - Gray nodes indicate inactive IK/FK state.\n"
                "  - Green-bordered nodes have active connections.\n"
                "  - Press 'F' in a graph to fit all nodes in view."
            ),
            button=["OK"],
            defaultButton="OK",
        )

    def _open_batch_window(self):
        try:
            self._batch_window.close()
            self._batch_window.deleteLater()
        except Exception:
            pass
        self._batch_window = BatchExport()
        self._batch_window.show()

    def _open_constraint_window(self):
        try:
            self._constraint_window.close()
            self._constraint_window.deleteLater()
        except Exception:
            pass
        self._constraint_window = ConstraintManager()
        self._constraint_window.show()

    # ============================================================ lifecycle

    def closeEvent(self, event):
        for jid in self.script_job_ids:
            if cmds.scriptJob(exists=jid):
                cmds.scriptJob(kill=jid)
        super(RetargetingTool, self).closeEvent(event)


# ============================================================ entry point

def start():
    global _retarget_tool_ui
    try:
        _retarget_tool_ui.close()
        _retarget_tool_ui.deleteLater()
    except Exception:
        pass
    _retarget_tool_ui = RetargetingTool()
    _retarget_tool_ui.show()


_retarget_tool_ui = None

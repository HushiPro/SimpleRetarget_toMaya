"""
MatchingPanel — centre column with a slot-based mapping system.
Users create slots from the source hierarchy, then assign target nodes
into those slots to define the retargeting correspondence.
"""
import maya.cmds as cmds

from .compat import QtCore, QtGui, QtWidgets
from .constants import (
    COLORS, SLOT_WIDTH, SLOT_DEPTH_GAP, SLOT_SIBLING_GAP,
)
from . import core
from .core import SlotData
from .graph_items import SlotNodeItem, SlotEdgeItem, measure_slot_width
from .hypergraph_widget import ZoomableGraphicsView


DEFAULT_MIRROR_PAIRS = [
    ("_L", "_R"),
    ("_l", "_r"),
    ("_Left", "_Right"),
    ("_left", "_right"),
]


class MirrorSuffixEditor(QtWidgets.QDialog):
    """Dialog for editing mirror symmetry suffix pairs."""

    def __init__(self, pairs, parent=None):
        super(MirrorSuffixEditor, self).__init__(parent)
        self.setWindowTitle("Mirror Suffix Pairs")
        self.setMinimumSize(320, 260)

        self._table = QtWidgets.QTableWidget(len(pairs), 2)
        self._table.setHorizontalHeaderLabels(["Left Suffix", "Right Suffix"])
        self._table.horizontalHeader().setStretchLastSection(True)
        for i, (left, right) in enumerate(pairs):
            self._table.setItem(i, 0, QtWidgets.QTableWidgetItem(left))
            self._table.setItem(i, 1, QtWidgets.QTableWidgetItem(right))

        add_btn = QtWidgets.QPushButton("+")
        add_btn.setFixedWidth(32)
        remove_btn = QtWidgets.QPushButton("\u2212")
        remove_btn.setFixedWidth(32)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()

        ok_btn = QtWidgets.QPushButton("OK")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        dialog_btns = QtWidgets.QHBoxLayout()
        dialog_btns.addStretch()
        dialog_btns.addWidget(ok_btn)
        dialog_btns.addWidget(cancel_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(btn_row)
        layout.addLayout(dialog_btns)

        add_btn.clicked.connect(self._add_row)
        remove_btn.clicked.connect(self._remove_row)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def _add_row(self):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QtWidgets.QTableWidgetItem("_L"))
        self._table.setItem(row, 1, QtWidgets.QTableWidgetItem("_R"))

    def _remove_row(self):
        row = self._table.currentRow()
        if row >= 0:
            self._table.removeRow(row)

    def get_pairs(self):
        pairs = []
        for i in range(self._table.rowCount()):
            left_item = self._table.item(i, 0)
            right_item = self._table.item(i, 1)
            if left_item and right_item:
                l, r = left_item.text().strip(), right_item.text().strip()
                if l and r:
                    pairs.append((l, r))
        return pairs


class MatchingPanel(QtWidgets.QWidget):
    """Centre panel: slot management for matching source → target."""

    def __init__(self, parent_tool):
        super(MatchingPanel, self).__init__()
        self.parent_tool = parent_tool

        self.slot_data_list = []    # all SlotData objects
        self.slot_items = {}        # source_name → SlotNodeItem
        self.slot_edges = []

        # graph view
        self._scene = QtWidgets.QGraphicsScene(self)
        self._view = ZoomableGraphicsView()
        self._view.setScene(self._scene)

        # title
        title_label = QtWidgets.QLabel("Matching")
        title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #ccc;")
        title_label.setAlignment(QtCore.Qt.AlignCenter)

        # toolbar
        self.add_slot_btn = QtWidgets.QPushButton("+ Add Slots from Source")
        self.add_slot_btn.setToolTip(
            "Select nodes in the source graph, then click to create matching slots")
        self.remove_target_btn = QtWidgets.QPushButton("Remove Target")
        self.remove_target_btn.setToolTip(
            "Remove target assignment from selected slot")
        self.clear_slots_btn = QtWidgets.QPushButton("Clear All")

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(self.add_slot_btn)
        toolbar.addWidget(self.remove_target_btn)
        toolbar.addWidget(self.clear_slots_btn)

        # mirror symmetry
        self._mirror_pairs = list(DEFAULT_MIRROR_PAIRS)
        self.mirror_checkbox = QtWidgets.QRadioButton("Mirror Symmetry")
        self.mirror_checkbox.setAutoExclusive(False)
        self.mirror_checkbox.setToolTip(
            "Automatically add/assign mirrored counterparts based on L/R suffixes")
        self.edit_suffixes_btn = QtWidgets.QPushButton("Edit Suffixes...")
        self.edit_suffixes_btn.setToolTip("Customize mirror suffix pairs")

        mirror_layout = QtWidgets.QHBoxLayout()
        mirror_layout.addWidget(self.mirror_checkbox)
        mirror_layout.addWidget(self.edit_suffixes_btn)
        mirror_layout.addStretch()

        # status label
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)

        # assemble
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title_label)
        layout.addLayout(toolbar)
        layout.addLayout(mirror_layout)
        layout.addWidget(self._view)
        layout.addWidget(self.status_label)

        # signals
        self.add_slot_btn.clicked.connect(self._add_slots_from_source)
        self.clear_slots_btn.clicked.connect(self.clear_all_slots)
        self.remove_target_btn.clicked.connect(self._remove_target_from_selected)
        self.edit_suffixes_btn.clicked.connect(self._open_suffix_editor)

    # -------------------------------------------------------- public API

    def assign_target_to_slot(self, slot_item):
        """Assign the currently-selected target graph node to *slot_item*.
        When mirror symmetry is enabled, also assigns the mirrored target
        to the mirrored slot if both exist."""
        target_graph = self.parent_tool.target_panel.hypergraph
        selected = target_graph.get_selected_node_names()
        if not selected:
            cmds.warning("Select a node in the target graph first!")
            return

        target_name = selected[0]
        slot_item.slot_data.target_node = target_name
        slot_item._update_tooltip()
        slot_item.update()

        if self.mirror_checkbox.isChecked():
            source_name = slot_item.slot_data.source_node
            slot_names = {s.source_node for s in self.slot_data_list}
            target_names = set(target_graph.node_data_map.keys())

            mirror_source = self._find_mirror_name(source_name, slot_names)
            mirror_target = self._find_mirror_name(target_name, target_names)

            if mirror_source and mirror_target and mirror_source in self.slot_items:
                mirror_slot_item = self.slot_items[mirror_source]
                mirror_slot_item.slot_data.target_node = mirror_target
                mirror_slot_item._update_tooltip()
                mirror_slot_item.update()

        self._rebuild_slot_graph()

    def disconnect_slot(self, slot_item):
        """Disconnect a single slot: remove Maya constraints, clear target,
        and remove the connected visual."""
        if slot_item.slot_data.target_node:
            core.disconnect_single(slot_item.slot_data.target_node)
        slot_item.slot_data.target_node = None
        slot_item._connected = False
        slot_item._update_tooltip()
        self._rebuild_slot_graph()

    def mark_slots_connected(self, connected_sources):
        """Update the connected visual on slot items."""
        for source_name, item in self.slot_items.items():
            item._connected = source_name in connected_sources
            item.update()

    def remove_slot(self, slot_data):
        """Remove a single slot (called from context menu)."""
        if slot_data in self.slot_data_list:
            self.slot_data_list.remove(slot_data)
        source_graph = self.parent_tool.source_panel.hypergraph
        self._rebuild_slot_hierarchy(source_graph)
        self._rebuild_slot_graph()

    def relayout_slots(self):
        """Rebuild the slot graph after text/width changes."""
        self._rebuild_slot_graph()

    def clear_all_slots(self):
        self._scene.clear()
        self.slot_data_list.clear()
        self.slot_items.clear()
        self.slot_edges.clear()
        self._update_status()

    def get_all_mappings(self):
        """Return ``[(source, target, is_ik), ...]`` for assigned slots."""
        return [
            (s.source_node, s.target_node, s.is_ik)
            for s in self.slot_data_list
            if s.target_node
        ]

    # -------------------------------------------------------- internals

    def _add_slots_from_source(self):
        source_graph = self.parent_tool.source_panel.hypergraph
        selected = source_graph.get_selected_node_names()
        if not selected:
            cmds.warning("Select nodes in the source graph first!")
            return

        names_to_add = list(selected)
        if self.mirror_checkbox.isChecked():
            all_source_names = set(source_graph.node_data_map.keys())
            for name in selected:
                mirror = self._find_mirror_name(name, all_source_names)
                if mirror and mirror not in names_to_add:
                    names_to_add.append(mirror)

        existing = {s.source_node for s in self.slot_data_list}
        for name in names_to_add:
            if name in existing:
                continue
            self.slot_data_list.append(SlotData(name))

        self._rebuild_slot_hierarchy(source_graph)
        self._rebuild_slot_graph()

    def _rebuild_slot_hierarchy(self, source_graph):
        """Rebuild all slot parent-child relationships from the source graph
        hierarchy.  Works regardless of the order slots were created."""
        slot_by_name = {s.source_node: s for s in self.slot_data_list}

        for slot in self.slot_data_list:
            slot.parent_slot = None
            slot.children = []

        for slot in self.slot_data_list:
            node_data = source_graph.node_data_map.get(slot.source_node)
            if not node_data:
                continue
            current = node_data.parent_name
            while current:
                if current in slot_by_name:
                    slot.parent_slot = slot_by_name[current]
                    slot_by_name[current].children.append(slot)
                    break
                pd = source_graph.node_data_map.get(current)
                current = pd.parent_name if pd else None

    def _find_mirror_name(self, name, available_names):
        """Return the mirrored counterpart of *name* if it exists in
        *available_names*, otherwise ``None``."""
        for left_suffix, right_suffix in self._mirror_pairs:
            if name.endswith(left_suffix):
                mirror = name[:-len(left_suffix)] + right_suffix
                if mirror in available_names:
                    return mirror
            elif name.endswith(right_suffix):
                mirror = name[:-len(right_suffix)] + left_suffix
                if mirror in available_names:
                    return mirror
        return None

    def _open_suffix_editor(self):
        dlg = MirrorSuffixEditor(self._mirror_pairs, self)
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            self._mirror_pairs = dlg.get_pairs()

    def _remove_target_from_selected(self):
        for item in self._scene.selectedItems():
            if isinstance(item, SlotNodeItem):
                item.slot_data.target_node = None
                item._update_tooltip()
                item.update()
        self._rebuild_slot_graph()

    # -------------------------------------------------------- rebuild graph

    def _rebuild_slot_graph(self):
        had_items = bool(self.slot_items)
        saved_transform = self._view.transform()
        saved_center = self._view.mapToScene(
            self._view.viewport().rect().center())

        self._scene.clear()
        self.slot_items.clear()
        self.slot_edges.clear()

        root_slots = [s for s in self.slot_data_list if s.parent_slot is None]

        x_offset = 0
        for root in root_slots:
            sw = self._subtree_width(root)
            self._position_subtree(root, x_offset, 0)
            x_offset += sw + SLOT_SIBLING_GAP * 3

        # edges
        for slot in self.slot_data_list:
            parent_src = slot.parent_slot.source_node if slot.parent_slot else None
            if parent_src and parent_src in self.slot_items and slot.source_node in self.slot_items:
                edge = SlotEdgeItem(
                    self.slot_items[parent_src],
                    self.slot_items[slot.source_node],
                )
                self._scene.addItem(edge)
                self.slot_edges.append(edge)

        if self.slot_items:
            if had_items:
                self._view.setTransform(saved_transform)
                self._view.centerOn(saved_center)
            else:
                first_item = next(iter(self.slot_items.values()))
                self._view.center_on_root(first_item)
        self._update_status()

    def _subtree_width(self, slot):
        slot_width = self._slot_width(slot)
        if not slot.children:
            return slot_width
        w = sum(self._subtree_width(c) for c in slot.children)
        w += SLOT_SIBLING_GAP * (len(slot.children) - 1)
        return max(slot_width, w)

    def _slot_width(self, slot):
        item = self.slot_items.get(slot.source_node)
        if item:
            return item.boundingRect().width()
        return measure_slot_width(slot)

    def _position_subtree(self, slot, x, y):
        sw = self._subtree_width(slot)
        item = SlotNodeItem(slot, self)
        self._scene.addItem(item)
        item.setPos(x + (sw - item.boundingRect().width()) / 2, y)
        self.slot_items[slot.source_node] = item

        if slot.children:
            cx = x
            for child in slot.children:
                cw = self._subtree_width(child)
                self._position_subtree(child, cx, y + SLOT_DEPTH_GAP)
                cx += cw + SLOT_SIBLING_GAP

    def _update_status(self):
        total = len(self.slot_data_list)
        assigned = sum(1 for s in self.slot_data_list if s.target_node)
        if total == 0:
            self.status_label.setText("")
        else:
            self.status_label.setText(
                "{} / {} slots assigned".format(assigned, total))

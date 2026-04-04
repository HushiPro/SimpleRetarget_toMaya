"""
Zoomable QGraphicsView base and HypergraphWidget that visualises a
bone / curve hierarchy as an interactive horizontal flow graph
(root on the left, children branching to the right — ideal for
tall / portrait panels).
"""
import maya.cmds as cmds

from .compat import QtCore, QtGui, QtWidgets
from .constants import (
    COLORS, NODE_WIDTH, NODE_HEIGHT,
    GRAPH_DEPTH_GAP, GRAPH_SIBLING_GAP,
)
from . import core
from .graph_items import GraphNodeItem, GraphEdgeItem


class ZoomableGraphicsView(QtWidgets.QGraphicsView):
    """QGraphicsView with mouse-wheel zoom and middle-button pan."""

    def __init__(self, parent=None):
        super(ZoomableGraphicsView, self).__init__(parent)
        self._zoom = 1.0
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.setStyleSheet(
            "background-color: {}; border: 1px solid #333;".format(COLORS['bg']))

    def wheelEvent(self, event):
        delta = event.angleDelta().y() if hasattr(event, 'angleDelta') else event.delta()
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        new_zoom = self._zoom * factor
        if 0.05 < new_zoom < 10.0:
            self._zoom = new_zoom
            self.scale(factor, factor)

    def fit_contents(self):
        """Fit scene into view, but guarantee nodes stay readable."""
        if not self.scene():
            return
        sr = self.scene().sceneRect()
        if sr.isEmpty():
            return
        padded = sr.adjusted(-40, -40, 40, 40)
        self.fitInView(padded, QtCore.Qt.KeepAspectRatio)
        # Clamp so nodes are never smaller than ~120 px on screen
        cur_scale = self.transform().m11()
        max_node_width = max(
            [item.rect().width() for item in self.node_items.values()] or [NODE_WIDTH]
        )
        min_scale = 120.0 / max(max_node_width, 1)
        if cur_scale < min_scale:
            ratio = min_scale / cur_scale
            self.scale(ratio, ratio)
        self._zoom = self.transform().m11()

    def center_on_root(self, root_item):
        """Show *root_item* at 1:1 scale near the top-left of the view."""
        self.resetTransform()
        self._zoom = 1.0
        if root_item:
            self.centerOn(root_item)

    def keyPressEvent(self, event):
        if event.key() == QtCore.Qt.Key_F:
            self.fit_contents()
        else:
            super(ZoomableGraphicsView, self).keyPressEvent(event)


class HypergraphWidget(ZoomableGraphicsView):
    """Displays a bone or curve hierarchy as an interactive **horizontal**
    flow graph (root left → children right)."""

    node_selected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(HypergraphWidget, self).__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self.node_items = {}        # name → GraphNodeItem
        self.edge_items = []
        self.node_data_map = {}     # name → NodeData
        self.root_nodes = []
        self._programmatic_select = False

    # -------------------------------------------------------- public API

    def build_graph(self, root_name, mode='bone'):
        """Build the graph from a Maya hierarchy root.

        *mode*: ``'bone'`` for joints, ``'curve'`` for NURBS-curve transforms.
        """
        self.clear_graph()
        if not root_name or not cmds.objExists(root_name):
            return

        if mode == 'bone':
            self.node_data_map, self.root_nodes = core.collect_bones(root_name)
        else:
            self.node_data_map, self.root_nodes = core.collect_curves(root_name)

        if not self.node_data_map:
            return

        core.detect_ik_fk(self.node_data_map)

        for name, data in self.node_data_map.items():
            item = GraphNodeItem(data, self)
            self._scene.addItem(item)
            self.node_items[name] = item

        for name, data in self.node_data_map.items():
            if data.parent_name and data.parent_name in self.node_items:
                edge = GraphEdgeItem(
                    self.node_items[data.parent_name], self.node_items[name])
                self._scene.addItem(edge)
                self.edge_items.append(edge)

        self._layout_tree()
        for edge in self.edge_items:
            edge.update_path()

        # Show at 1:1 zoom centered on the first root
        first_root_item = self.node_items.get(
            self.root_nodes[0]) if self.root_nodes else None
        self.center_on_root(first_root_item)

    def clear_graph(self):
        self._scene.clear()
        self.node_items.clear()
        self.edge_items.clear()
        self.node_data_map.clear()
        self.root_nodes.clear()

    def get_selected_node_names(self):
        return [
            item.node_data.name
            for item in self._scene.selectedItems()
            if isinstance(item, GraphNodeItem)
        ]

    def refresh_ik_fk_states(self):
        core.detect_ik_fk(self.node_data_map)
        for name, item in self.node_items.items():
            if name in self.node_data_map:
                item.node_data = self.node_data_map[name]
                item.refresh_appearance()

    def sync_selection_from_maya(self):
        """Highlight graph nodes that correspond to the current Maya selection."""
        if self._programmatic_select:
            return
        maya_sel = set(cmds.ls(selection=True, long=False) or [])
        for name, item in self.node_items.items():
            item.setSelected(name in maya_sel)

    # -------------------------------------------------------- horizontal layout

    def _layout_tree(self):
        """Lay out nodes as a horizontal tree (root left → children right)."""
        for root in self.root_nodes:
            self._compute_depth(root, 0)

        y_offset = 0
        for root in self.root_nodes:
            sh = self._subtree_height(root)
            self._position_subtree(root, 0, y_offset)
            y_offset += sh + GRAPH_SIBLING_GAP * 3

    def _node_width(self, name):
        item = self.node_items.get(name)
        return item.rect().width() if item else NODE_WIDTH

    def _compute_depth(self, name, depth):
        data = self.node_data_map.get(name)
        if not data:
            return
        data.depth = depth
        for child in data.children:
            self._compute_depth(child, depth + 1)

    def _subtree_height(self, name):
        """Total vertical space needed for *name* and all its descendants."""
        data = self.node_data_map.get(name)
        if not data or not data.children:
            return NODE_HEIGHT
        h = sum(self._subtree_height(c) for c in data.children)
        h += GRAPH_SIBLING_GAP * (len(data.children) - 1)
        return max(NODE_HEIGHT, h)

    def _position_subtree(self, name, x, y):
        sh = self._subtree_height(name)
        item = self.node_items.get(name)
        if item:
            item.setPos(x, y + (sh - NODE_HEIGHT) / 2)

        data = self.node_data_map.get(name)
        if data and data.children:
            child_y = y
            child_x = x + self._node_width(name) + GRAPH_DEPTH_GAP
            for child in data.children:
                ch = self._subtree_height(child)
                self._position_subtree(child, child_x, child_y)
                child_y += ch + GRAPH_SIBLING_GAP

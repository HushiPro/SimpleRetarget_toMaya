"""
QGraphicsItem subclasses for the hypergraph nodes / edges and matching-panel
slot nodes / edges.
"""
import maya.cmds as cmds

from .compat import QtCore, QtGui, QtWidgets
from .constants import (
    COLORS, NODE_WIDTH, NODE_HEIGHT, NODE_RADIUS,
    SLOT_WIDTH, SLOT_HEIGHT,
)


# ============================================================
#  Hypergraph items
# ============================================================

class GraphNodeItem(QtWidgets.QGraphicsRectItem):
    """Interactive node representing a bone or curve controller."""

    def __init__(self, node_data, hypergraph_widget):
        super(GraphNodeItem, self).__init__(0, 0, NODE_WIDTH, NODE_HEIGHT)
        self.node_data = node_data
        self.hypergraph_widget = hypergraph_widget
        self._hovered = False

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(node_data.name)

        self.label = QtWidgets.QGraphicsTextItem(self)
        font = QtGui.QFont("Segoe UI", 10)
        self.label.setFont(font)
        self.label.setDefaultTextColor(QtGui.QColor(COLORS['text']))

        display_name = node_data.name
        if len(display_name) > 22:
            display_name = display_name[:20] + '..'
        self.label.setPlainText(display_name)

        text_rect = self.label.boundingRect()
        self.label.setPos(
            (NODE_WIDTH - text_rect.width()) / 2,
            (NODE_HEIGHT - text_rect.height()) / 2,
        )

    # ---- appearance helpers ----

    def _fill_color(self):
        nd = self.node_data
        # IK/FK graying
        if nd.ik_fk_value >= 0:
            if nd.is_ik and nd.ik_fk_value > 0.5:
                return COLORS['node_ik_inactive']
            if not nd.is_ik and nd.ik_fk_value <= 0.5:
                return COLORS['node_fk_inactive']
        if nd.node_type == 'joint':
            return COLORS['node_bone_hover'] if self._hovered else COLORS['node_bone']
        return COLORS['node_curve_hover'] if self._hovered else COLORS['node_curve']

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        border_color = COLORS['node_selected'] if self.isSelected() else '#444444'
        pen_width = 2.5 if self.isSelected() else 1.5
        painter.setPen(QtGui.QPen(QtGui.QColor(border_color), pen_width))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(self._fill_color())))
        painter.drawRoundedRect(self.rect(), NODE_RADIUS, NODE_RADIUS)

    # ---- interaction ----

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(GraphNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super(GraphNodeItem, self).hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        super(GraphNodeItem, self).mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            self.hypergraph_widget._programmatic_select = True
            try:
                if event.modifiers() & QtCore.Qt.ControlModifier:
                    cmds.select(self.node_data.name, add=True)
                else:
                    cmds.select(self.node_data.name, replace=True)
            finally:
                self.hypergraph_widget._programmatic_select = False
            self.hypergraph_widget.node_selected.emit(self.node_data.name)

    def refresh_appearance(self):
        self.update()


class GraphEdgeItem(QtWidgets.QGraphicsPathItem):
    """Bezier edge connecting a parent node to a child node."""

    def __init__(self, parent_item, child_item):
        super(GraphEdgeItem, self).__init__()
        self.parent_item = parent_item
        self.child_item = child_item

        pen = QtGui.QPen(QtGui.QColor(COLORS['edge']), 2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        self.setPen(pen)
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        pr = self.parent_item.sceneBoundingRect()
        cr = self.child_item.sceneBoundingRect()
        # horizontal: right-centre of parent → left-centre of child
        sx, sy = pr.right(), pr.center().y()
        ex, ey = cr.left(), cr.center().y()
        mid_x = (sx + ex) / 2
        path = QtGui.QPainterPath()
        path.moveTo(sx, sy)
        path.cubicTo(mid_x, sy, mid_x, ey, ex, ey)
        self.setPath(path)


# ============================================================
#  Matching-panel slot items
# ============================================================

class SlotNodeItem(QtWidgets.QGraphicsItem):
    """Bifrost-style slot node showing a source → target mapping."""

    def __init__(self, slot_data, matching_panel):
        super(SlotNodeItem, self).__init__()
        self.slot_data = slot_data
        self.matching_panel = matching_panel
        self._hovered = False
        self._connected = False

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update_tooltip()

    def _update_tooltip(self):
        target = self.slot_data.target_node or '(empty)'
        mode = ' [IK]' if self.slot_data.is_ik else ''
        self.setToolTip("Source: {}\nTarget: {}{}".format(
            self.slot_data.source_node, target, mode))

    # ---- geometry / paint ----

    def boundingRect(self):
        return QtCore.QRectF(0, 0, SLOT_WIDTH, SLOT_HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.boundingRect()

        # background & border
        if self._connected:
            bg = QtGui.QColor(COLORS['node_connected_bg'])
            border = QtGui.QColor(COLORS['node_connected_border'])
            pen_width = 2.5
        elif self.isSelected():
            bg = QtGui.QColor('#3a5570')
            border = QtGui.QColor(COLORS['accent'])
            pen_width = 2
        elif self._hovered:
            bg = QtGui.QColor('#363636')
            border = QtGui.QColor('#666666')
            pen_width = 2
        else:
            bg = QtGui.QColor(COLORS['slot_bg'])
            border = QtGui.QColor(COLORS['slot_border'])
            pen_width = 2

        painter.setPen(QtGui.QPen(border, pen_width))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 10, 10)

        mid_x = rect.width() / 2

        # centre divider
        painter.setPen(QtGui.QPen(QtGui.QColor('#444444'), 1))
        painter.drawLine(
            QtCore.QPointF(mid_x, 6),
            QtCore.QPointF(mid_x, rect.height() - 6),
        )

        font = QtGui.QFont("Segoe UI", 10)
        painter.setFont(font)

        # IK badge
        if self.slot_data.is_ik:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor('#d9534f'))
            painter.drawRoundedRect(QtCore.QRectF(mid_x - 28, 3, 24, 15), 4, 4)
            painter.setPen(QtGui.QColor('#ffffff'))
            tiny = QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold)
            painter.setFont(tiny)
            painter.drawText(QtCore.QRectF(mid_x - 28, 3, 24, 15),
                             QtCore.Qt.AlignCenter, "IK")
            painter.setFont(font)

        # source port dot
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(COLORS['slot_source']))
        painter.drawEllipse(QtCore.QPointF(12, rect.height() / 2), 5, 5)

        # source name
        painter.setPen(QtGui.QColor(COLORS['text_bright']))
        src = self.slot_data.source_node
        if len(src) > 18:
            src = src[:16] + '..'
        painter.drawText(
            QtCore.QRectF(24, 0, mid_x - 34, rect.height()),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, src,
        )

        # arrow
        painter.setPen(QtGui.QColor('#888888'))
        painter.setFont(QtGui.QFont("Segoe UI", 12))
        painter.drawText(
            QtCore.QRectF(mid_x - 10, 0, 20, rect.height()),
            QtCore.Qt.AlignCenter, u"\u2192",
        )

        # target side
        painter.setFont(font)
        if self.slot_data.target_node:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(COLORS['slot_target']))
            painter.drawEllipse(
                QtCore.QPointF(rect.width() - 12, rect.height() / 2), 5, 5)
            painter.setPen(QtGui.QColor(COLORS['text_bright']))
            tgt = self.slot_data.target_node
            if len(tgt) > 18:
                tgt = tgt[:16] + '..'
            painter.drawText(
                QtCore.QRectF(mid_x + 8, 0, mid_x - 24, rect.height()),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, tgt,
            )
        else:
            painter.setPen(QtGui.QColor(COLORS['text_dim']))
            painter.drawText(
                QtCore.QRectF(mid_x + 8, 0, mid_x - 24, rect.height()),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "(assign target)",
            )

    # ---- interaction ----

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(SlotNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super(SlotNodeItem, self).hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        super(SlotNodeItem, self).mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            if event.pos().x() > SLOT_WIDTH / 2:
                self.matching_panel.assign_target_to_slot(self)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        ik_action = menu.addAction("Toggle IK Mode")
        remove_tgt = menu.addAction("Remove Target")
        disconnect_action = menu.addAction("Disconnect")
        disconnect_action.setEnabled(self._connected)
        menu.addSeparator()
        remove_slot = menu.addAction("Delete Slot")

        chosen = menu.exec_(event.screenPos())
        if chosen == ik_action:
            self.slot_data.is_ik = not self.slot_data.is_ik
            self._update_tooltip()
            self.update()
        elif chosen == remove_tgt:
            self.slot_data.target_node = None
            self._update_tooltip()
            self.update()
        elif chosen == disconnect_action:
            self.matching_panel.disconnect_slot(self)
        elif chosen == remove_slot:
            self.matching_panel.remove_slot(self.slot_data)


class SlotEdgeItem(QtWidgets.QGraphicsPathItem):
    """Hierarchy connection between slot nodes."""

    def __init__(self, parent_slot_item, child_slot_item):
        super(SlotEdgeItem, self).__init__()
        self.parent_slot_item = parent_slot_item
        self.child_slot_item = child_slot_item

        pen = QtGui.QPen(QtGui.QColor(COLORS['edge']), 2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        self.setPen(pen)
        self.setZValue(-1)
        self.update_path()

    def update_path(self):
        pr = self.parent_slot_item.sceneBoundingRect()
        cr = self.child_slot_item.sceneBoundingRect()
        sx, sy = pr.center().x(), pr.bottom()
        ex, ey = cr.center().x(), cr.top()
        path = QtGui.QPainterPath()
        path.moveTo(sx, sy)
        mid_y = (sy + ey) / 2
        path.cubicTo(sx, mid_y, ex, mid_y, ex, ey)
        self.setPath(path)

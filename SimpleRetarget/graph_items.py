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


def _text_width(metrics, text):
    """Cross-version text width measurement (Qt 5.11+ / Qt 6)."""
    if hasattr(metrics, 'horizontalAdvance'):
        return metrics.horizontalAdvance(text)
    return metrics.width(text)


_SLOT_FONT = None
_SLOT_METRICS = None


def _slot_font_and_metrics():
    global _SLOT_FONT, _SLOT_METRICS
    if _SLOT_FONT is None:
        _SLOT_FONT = QtGui.QFont("Segoe UI", 10)
        _SLOT_METRICS = QtGui.QFontMetrics(_SLOT_FONT)
    return _SLOT_FONT, _SLOT_METRICS


def measure_graph_node_width(name):
    font = QtGui.QFont("Segoe UI", 10)
    metrics = QtGui.QFontMetrics(font)
    return max(NODE_WIDTH, _text_width(metrics, name) + 32)


# Padding budget inside a slot:
#   left-dot(24) + source_text + gap(16) + arrow(20) + gap(16) + target_text + right-dot(24)
_SLOT_FIXED_PADDING = 100


def measure_slot_width(slot_data):
    _, metrics = _slot_font_and_metrics()
    src_w = _text_width(metrics, slot_data.source_node or "")
    tgt_w = _text_width(metrics, slot_data.target_node or "(assign target)")
    flag_extra = 0
    if slot_data.rotation_override is False:
        flag_extra += 36
    if slot_data.translation_override is False:
        flag_extra += 36
    return max(SLOT_WIDTH, src_w + tgt_w + _SLOT_FIXED_PADDING + flag_extra)


def compute_slot_divider_x(slot_data, total_width):
    """Return the x-coordinate of the centre divider for a given slot."""
    _, metrics = _slot_font_and_metrics()
    src_w = _text_width(metrics, slot_data.source_node or "")
    tgt_w = _text_width(metrics, slot_data.target_node or "(assign target)")

    available = total_width - _SLOT_FIXED_PADDING
    if src_w + tgt_w > 0:
        ratio = src_w / float(src_w + tgt_w)
    else:
        ratio = 0.5
    divider = 24 + available * ratio + 16
    divider = max(total_width * 0.2, min(divider, total_width * 0.8))
    return divider


# ============================================================
#  Hypergraph items
# ============================================================

class GraphNodeItem(QtWidgets.QGraphicsRectItem):
    """Interactive node representing a bone or curve controller."""

    def __init__(self, node_data, hypergraph_widget):
        super(GraphNodeItem, self).__init__(
            0, 0, measure_graph_node_width(node_data.name), NODE_HEIGHT)
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
        self.label.setPlainText(node_data.name)

        text_rect = self.label.boundingRect()
        self.label.setPos(
            (self.rect().width() - text_rect.width()) / 2,
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
        if nd.node_type == 'locator':
            return COLORS['node_locator_hover'] if self._hovered else COLORS['node_locator']
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
        self._width = measure_slot_width(slot_data)

        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update_tooltip()

    def _update_tooltip(self):
        target = self.slot_data.target_node or '(empty)'
        mode = ' [IK]' if self.slot_data.is_ik else ''
        self._width = measure_slot_width(self.slot_data)
        def _fmt(opt):
            if opt is None:
                return "Global"
            return "On" if opt else "Off"

        self.setToolTip(
            "Source: {}\nTarget: {}{}\nRotation: {}\nTranslation: {}".format(
                self.slot_data.source_node,
                target,
                mode,
                _fmt(self.slot_data.rotation_override),
                _fmt(self.slot_data.translation_override),
            )
        )

    # ---- geometry / paint ----

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self._width, SLOT_HEIGHT)

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

        div_x = compute_slot_divider_x(self.slot_data, rect.width())

        # centre divider
        painter.setPen(QtGui.QPen(QtGui.QColor('#444444'), 1))
        painter.drawLine(
            QtCore.QPointF(div_x, 6),
            QtCore.QPointF(div_x, rect.height() - 6),
        )

        font, _ = _slot_font_and_metrics()
        painter.setFont(font)

        # IK badge
        if self.slot_data.is_ik:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor('#d9534f'))
            painter.drawRoundedRect(
                QtCore.QRectF(div_x - 28, 3, 24, 15), 4, 4)
            painter.setPen(QtGui.QColor('#ffffff'))
            tiny = QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold)
            painter.setFont(tiny)
            painter.drawText(QtCore.QRectF(div_x - 28, 3, 24, 15),
                             QtCore.Qt.AlignCenter, "IK")
            painter.setFont(font)

        # per-slot channel disable badges (override global)
        badge_x = div_x + 4
        if self.slot_data.rotation_override is False:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor('#f0ad4e'))
            painter.drawRoundedRect(QtCore.QRectF(badge_x, 3, 30, 15), 4, 4)
            painter.setPen(QtGui.QColor('#111111'))
            tiny = QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold)
            painter.setFont(tiny)
            painter.drawText(QtCore.QRectF(badge_x, 3, 30, 15),
                             QtCore.Qt.AlignCenter, "R off")
            badge_x += 34
            painter.setFont(font)

        if self.slot_data.translation_override is False:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor('#f0ad4e'))
            painter.drawRoundedRect(QtCore.QRectF(badge_x, 3, 30, 15), 4, 4)
            painter.setPen(QtGui.QColor('#111111'))
            tiny = QtGui.QFont("Segoe UI", 7, QtGui.QFont.Bold)
            painter.setFont(tiny)
            painter.drawText(QtCore.QRectF(badge_x, 3, 30, 15),
                             QtCore.Qt.AlignCenter, "T off")
            painter.setFont(font)

        # source port dot
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(COLORS['slot_source']))
        painter.drawEllipse(QtCore.QPointF(12, rect.height() / 2), 5, 5)

        # source name (full width from dot to divider)
        painter.setPen(QtGui.QColor(COLORS['text_bright']))
        painter.drawText(
            QtCore.QRectF(24, 0, div_x - 34, rect.height()),
            QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
            self.slot_data.source_node,
        )

        # arrow
        painter.setPen(QtGui.QColor('#888888'))
        painter.setFont(QtGui.QFont("Segoe UI", 12))
        painter.drawText(
            QtCore.QRectF(div_x - 10, 0, 20, rect.height()),
            QtCore.Qt.AlignCenter, u"\u2192",
        )

        # target side (full width from divider to right dot)
        painter.setFont(font)
        tgt_left = div_x + 8
        tgt_width = rect.width() - tgt_left - 24
        if self.slot_data.target_node:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(COLORS['slot_target']))
            painter.drawEllipse(
                QtCore.QPointF(rect.width() - 12, rect.height() / 2), 5, 5)
            painter.setPen(QtGui.QColor(COLORS['text_bright']))
            painter.drawText(
                QtCore.QRectF(tgt_left, 0, tgt_width, rect.height()),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                self.slot_data.target_node,
            )
        else:
            painter.setPen(QtGui.QColor(COLORS['text_dim']))
            painter.drawText(
                QtCore.QRectF(tgt_left, 0, tgt_width, rect.height()),
                QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                "(assign target)",
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
            div_x = compute_slot_divider_x(
                self.slot_data, self.boundingRect().width())
            if event.pos().x() > div_x:
                self.matching_panel.assign_target_to_slot(self)

    def contextMenuEvent(self, event):
        menu = QtWidgets.QMenu()
        ik_action = menu.addAction("Toggle IK Mode")
        remove_tgt = menu.addAction("Remove Target")
        disconnect_action = menu.addAction("Disconnect")
        disconnect_action.setEnabled(self._connected)
        menu.addSeparator()
        rot_enable = menu.addAction("Rotation")
        rot_enable.setCheckable(True)
        rot_enable.setChecked(self.slot_data.rotation_override is not False)

        tran_enable = menu.addAction("Translation")
        tran_enable.setCheckable(True)
        tran_enable.setChecked(self.slot_data.translation_override is not False)

        menu.addSeparator()
        remove_slot = menu.addAction("Delete Slot")

        chosen = menu.exec_(event.screenPos())
        if chosen == ik_action:
            self.slot_data.is_ik = not self.slot_data.is_ik
            self._update_tooltip()
            self.matching_panel.relayout_slots()
        elif chosen == remove_tgt:
            self.slot_data.target_node = None
            self._update_tooltip()
            self.matching_panel.relayout_slots()
        elif chosen == disconnect_action:
            self.matching_panel.disconnect_slot(self)
        elif chosen == rot_enable:
            self.slot_data.rotation_override = (
                None if rot_enable.isChecked() else False
            )
            self._update_tooltip()
            self.matching_panel.relayout_slots()
        elif chosen == tran_enable:
            self.slot_data.translation_override = (
                None if tran_enable.isChecked() else False
            )
            self._update_tooltip()
            self.matching_panel.relayout_slots()
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

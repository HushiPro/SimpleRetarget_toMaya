"""
Constraint manager dialog — visual list of plugin-generated constraints
with multi-select deletion support.
"""
import maya.cmds as cmds

from .compat import QtCore, QtGui, QtWidgets, maya_main_window
from .constants import COLORS, MAIN_STYLESHEET
from .hypergraph_widget import ZoomableGraphicsView
from . import core


def _measure_item_width(info):
    font = QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold)
    small_font = QtGui.QFont("Segoe UI", 9)
    bold_metrics = QtGui.QFontMetrics(font)
    small_metrics = QtGui.QFontMetrics(small_font)
    width = max(
        bold_metrics.horizontalAdvance(info["name"]),
        small_metrics.horizontalAdvance("Type: {}".format(info["type"])),
        small_metrics.horizontalAdvance("Target: {}".format(info["target_node"])),
    )
    return max(420, width + 36)


class ConstraintManagerView(ZoomableGraphicsView):
    def __init__(self, parent=None):
        super(ConstraintManagerView, self).__init__(parent)
        self.node_items = {}
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setRubberBandSelectionMode(QtCore.Qt.IntersectsItemShape)


class ConstraintNodeItem(QtWidgets.QGraphicsItem):
    HEIGHT = 70

    def __init__(self, constraint_info):
        super(ConstraintNodeItem, self).__init__()
        self.info = constraint_info
        self._hovered = False
        self._width = _measure_item_width(constraint_info)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setToolTip(
            "Constraint: {}\nType: {}\nTarget: {}\nSources: {}".format(
                self.info["name"],
                self.info["type"],
                self.info["target_node"] or "(unknown)",
                ", ".join(self.info["source_nodes"]) or "(none)",
            )
        )

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self._width, self.HEIGHT)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.boundingRect()

        if self.isSelected():
            fill = QtGui.QColor("#3a5570")
            border = QtGui.QColor(COLORS["accent"])
        elif self._hovered:
            fill = QtGui.QColor("#343434")
            border = QtGui.QColor("#666666")
        else:
            fill = QtGui.QColor(COLORS["slot_bg"])
            border = QtGui.QColor(COLORS["slot_border"])

        painter.setPen(QtGui.QPen(border, 2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 10, 10)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#d9534f"))
        painter.drawEllipse(QtCore.QPointF(16, rect.height() / 2), 6, 6)

        title_font = QtGui.QFont("Segoe UI", 10, QtGui.QFont.Bold)
        meta_font = QtGui.QFont("Segoe UI", 9)

        painter.setPen(QtGui.QColor(COLORS["text_bright"]))
        painter.setFont(title_font)
        painter.drawText(
            QtCore.QRectF(30, 8, rect.width() - 40, 20),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            self.info["name"],
        )

        painter.setPen(QtGui.QColor(COLORS["text"]))
        painter.setFont(meta_font)
        painter.drawText(
            QtCore.QRectF(30, 30, rect.width() - 40, 16),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            "Type: {}".format(self.info["type"]),
        )
        painter.drawText(
            QtCore.QRectF(30, 47, rect.width() - 40, 16),
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            "Target: {}".format(self.info["target_node"] or "(unknown)"),
        )

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super(ConstraintNodeItem, self).hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super(ConstraintNodeItem, self).hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        cmds.select(self.info["name"], replace=True)
        super(ConstraintNodeItem, self).mouseDoubleClickEvent(event)


class ConstraintManager(QtWidgets.QDialog):
    WINDOW_TITLE = "Generated Constraints"

    def __init__(self):
        super(ConstraintManager, self).__init__(maya_main_window())
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowFlags(
            self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(760, 520)
        self.setMinimumSize(520, 360)
        self.setStyleSheet(MAIN_STYLESHEET)

        if cmds.about(macOS=True):
            self.setWindowFlags(QtCore.Qt.Tool)

        self._scene = QtWidgets.QGraphicsScene(self)
        self._items = {}

        self._build_ui()
        self._build_connections()
        self.refresh_constraints()

    def _build_ui(self):
        self.view = ConstraintManagerView()
        self.view.setScene(self._scene)

        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.select_btn = QtWidgets.QPushButton("Select In Maya")
        self.delete_btn = QtWidgets.QPushButton("Delete Selected")
        self.delete_btn.setStyleSheet(
            "background-color: #b94a48; color: white; font-weight: bold;")
        self.close_btn = QtWidgets.QPushButton("Close")

        self.status_label = QtWidgets.QLabel("")
        self.status_label.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #888888; font-size: 11px;")

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.refresh_btn)
        button_row.addWidget(self.select_btn)
        button_row.addWidget(self.delete_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(button_row)
        layout.addWidget(self.view)
        layout.addWidget(self.status_label)

    def _build_connections(self):
        self.refresh_btn.clicked.connect(self.refresh_constraints)
        self.select_btn.clicked.connect(self.select_in_maya)
        self.delete_btn.clicked.connect(self.delete_selected_constraints)
        self.close_btn.clicked.connect(self.close)
        self._scene.selectionChanged.connect(self._update_status)

    def _selected_constraint_names(self):
        names = []
        for item in self._scene.selectedItems():
            if isinstance(item, ConstraintNodeItem):
                names.append(item.info["name"])
        return names

    def _update_status(self):
        total = len(self._items)
        selected = len(self._selected_constraint_names())
        self.status_label.setText(
            "{} constraints, {} selected".format(total, selected))

    def refresh_constraints(self):
        self._scene.clear()
        self._items = {}

        infos = core.get_generated_constraints_info()
        y = 0
        for info in infos:
            item = ConstraintNodeItem(info)
            item.setPos(0, y)
            self._scene.addItem(item)
            self._items[info["name"]] = item
            y += item.boundingRect().height() + 12

        if infos:
            self.view.fit_contents()
        self._update_status()

    def select_in_maya(self):
        names = self._selected_constraint_names()
        if not names:
            cmds.warning("Select one or more constraint nodes first.")
            return
        cmds.select(names, replace=True)

    def delete_selected_constraints(self):
        names = self._selected_constraint_names()
        if not names:
            cmds.warning("Select one or more constraint nodes first.")
            return

        result = cmds.confirmDialog(
            title="Delete Constraints",
            message="Delete {} selected generated constraint node(s)?".format(
                len(names)),
            button=["Yes", "No"],
            defaultButton="Yes",
            cancelButton="No",
        )
        if result != "Yes":
            return

        deleted = core.delete_generated_constraints(names)
        if deleted:
            cmds.select(clear=True)
        self.refresh_constraints()

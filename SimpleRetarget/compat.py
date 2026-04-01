"""
Qt version compatibility layer for Maya 2017+ (PySide2) and Maya 2025+ (PySide6).
"""
import sys
import maya.cmds as cmds
import maya.OpenMayaUI as omui

maya_version = int(cmds.about(version=True))

if maya_version < 2025:
    from shiboken2 import wrapInstance
    from PySide2 import QtCore, QtGui, QtWidgets
else:
    from shiboken6 import wrapInstance
    from PySide6 import QtCore, QtGui, QtWidgets


def maya_main_window():
    main_window = omui.MQtUtil.mainWindow()
    if sys.version_info.major >= 3:
        return wrapInstance(int(main_window), QtWidgets.QWidget)
    else:
        return wrapInstance(long(main_window), QtWidgets.QWidget)  # noqa: F821


def set_list_item_color(item, color):
    """Cross-version helper to set QListWidgetItem text color."""
    try:
        item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
    except AttributeError:
        item.setTextColor(QtGui.QColor(color))

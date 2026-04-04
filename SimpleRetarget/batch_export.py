"""
Batch exporter dialog — load multiple animation clips, bake onto a
connection rig, and export to FBX or Maya ASCII.
"""
import os

import maya.cmds as cmds
import maya.mel

from .compat import QtCore, QtGui, QtWidgets, maya_main_window, set_list_item_color
from . import core


class BatchExport(QtWidgets.QDialog):
    """Batch Bake & Export dialog (preserved from original tool)."""

    WINDOW_TITLE = "Batch Exporter"

    def __init__(self):
        super(BatchExport, self).__init__(maya_main_window())
        self.setWindowTitle(self.WINDOW_TITLE)
        self.setWindowFlags(
            self.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        self.resize(400, 250)
        self.animation_clip_paths = []
        self.output_folder = ""

        if cmds.about(macOS=True):
            self.setWindowFlags(QtCore.Qt.Tool)

        self._build_ui()
        self._build_connections()

    # -------------------------------------------------------- UI

    def _build_ui(self):
        self.file_list_widget = QtWidgets.QListWidget()

        self.remove_selected_button = QtWidgets.QPushButton("Remove Selected")
        self.remove_selected_button.setFixedHeight(24)
        self.load_anim_button = QtWidgets.QPushButton("Load Animations")
        self.load_anim_button.setFixedHeight(24)

        self.export_button = QtWidgets.QPushButton("Batch Export Animations")
        self.export_button.setStyleSheet(
            "background-color: lightgreen; color: black")

        self.connection_file_line = QtWidgets.QLineEdit()
        self.connection_file_line.setToolTip(
            "Enter the file path to the connection rig file.")
        self.connection_filepath_button = QtWidgets.QPushButton()
        self.connection_filepath_button.setIcon(QtGui.QIcon(":fileOpen.png"))
        self.connection_filepath_button.setFixedSize(24, 24)

        self.export_selected_label = QtWidgets.QLabel(
            "Export Selected (Optional):")
        self.export_selected_line = QtWidgets.QLineEdit()
        self.export_selected_line.setToolTip(
            "Enter the name(s) of nodes to export. Leave blank to export all.")
        self.export_selected_button = QtWidgets.QPushButton()
        self.export_selected_button.setIcon(QtGui.QIcon(":addClip.png"))
        self.export_selected_button.setFixedSize(24, 24)

        self.file_type_combo = QtWidgets.QComboBox()
        self.file_type_combo.addItems([".fbx", ".ma"])

        h1 = QtWidgets.QHBoxLayout()
        h1.addWidget(QtWidgets.QLabel("Connection Rig File:"))
        h1.addWidget(self.connection_file_line)
        h1.addWidget(self.connection_filepath_button)

        h2 = QtWidgets.QHBoxLayout()
        h2.addWidget(self.load_anim_button)
        h2.addWidget(self.remove_selected_button)

        h3 = QtWidgets.QHBoxLayout()
        h3.addWidget(QtWidgets.QLabel("Output File Type:"))
        h3.addWidget(self.file_type_combo)
        h3.addWidget(self.export_button)

        h4 = QtWidgets.QHBoxLayout()
        h4.addWidget(self.export_selected_label)
        h4.addWidget(self.export_selected_line)
        h4.addWidget(self.export_selected_button)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(self.file_list_widget)
        main_layout.addLayout(h2)
        main_layout.addLayout(h1)
        main_layout.addLayout(h4)
        main_layout.addLayout(h3)

    def _build_connections(self):
        self.connection_filepath_button.clicked.connect(
            self._connection_filepath_dialog)
        self.load_anim_button.clicked.connect(self._animation_filepath_dialog)
        self.export_button.clicked.connect(self._batch_action)
        self.export_selected_button.clicked.connect(self._add_selected_action)
        self.remove_selected_button.clicked.connect(self._remove_selected_item)

    # -------------------------------------------------------- actions

    def _connection_filepath_dialog(self):
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Connection Rig File", "",
            "Maya ASCII (*.ma);;All files (*.*)")
        if path[0]:
            self.connection_file_line.setText(path[0])

    def _animation_filepath_dialog(self):
        paths = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select Animation Clips", "",
            "Supported Files (*.fbx *.ma);;FBX (*.fbx);;Maya ASCII (*.ma);;All files (*.*)")
        file_list = paths[0]
        if file_list and file_list[0]:
            for p in file_list:
                self.file_list_widget.addItem(p)
        for i in range(self.file_list_widget.count()):
            set_list_item_color(self.file_list_widget.item(i), "white")

    def _import_animation_clip(self, clip_path):
        """Import one animation clip into the opened connection rig scene."""
        ext = os.path.splitext(clip_path)[1].lower()
        if ext == ".fbx":
            maya.mel.eval('FBXImportMode -v "exmerge";')
            maya.mel.eval('FBXImport -file "{}";'.format(clip_path))
            return
        if ext == ".ma":
            cmds.file(
                clip_path,
                i=True,
                type="mayaAscii",
                ignoreVersion=True,
                ra=True,
                mergeNamespacesOnClash=True,
                namespace=":",
                options="v=0;",
            )
            return
        raise RuntimeError("Unsupported animation file: {}".format(clip_path))

    def _add_selected_action(self):
        selection = cmds.ls(selection=True)
        if not selection:
            return
        if len(selection) > 1:
            text = "[" + ", ".join('"{}"'.format(s) for s in selection) + "]"
        else:
            text = selection[0]
        self.export_selected_line.setText(text)

    def _remove_selected_item(self):
        for item in self.file_list_widget.selectedItems():
            self.file_list_widget.takeItem(self.file_list_widget.row(item))

    def _batch_action(self):
        if not self.connection_file_line.text():
            cmds.warning("Connection file field is empty. Add a connection rig file.")
            return
        if self.file_list_widget.count() == 0:
            cmds.warning("Animation clip list is empty. Add clips to export!")
            return
        if self._output_filepath_dialog():
            self._bake_export()

    def _output_filepath_dialog(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select export folder path", "")
        if folder:
            self.output_folder = folder
            return True
        return False

    # -------------------------------------------------------- bake / export

    def _bake_export(self):
        self.animation_clip_paths = []
        for i in range(self.file_list_widget.count()):
            self.animation_clip_paths.append(
                self.file_list_widget.item(i).text())

        num_ops = len(self.animation_clip_paths) * 3
        progress = QtWidgets.QProgressDialog(
            "Preparing", "Cancel", 0, num_ops, self)
        progress.setWindowFlags(
            progress.windowFlags() ^ QtCore.Qt.WindowCloseButtonHint)
        progress.setWindowFlags(
            progress.windowFlags() ^ QtCore.Qt.WindowContextHelpButtonHint)
        progress.setValue(0)
        progress.setWindowTitle("Progress...")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()
        QtCore.QCoreApplication.processEvents()

        export_result = []

        for idx, clip_path in enumerate(self.animation_clip_paths):
            progress.setLabelText(
                "Baking and exporting {} of {}".format(
                    idx + 1, len(self.animation_clip_paths)))
            set_list_item_color(self.file_list_widget.item(idx), "yellow")

            cmds.file(new=True, force=True)
            cmds.file(self.connection_file_line.text(), open=True)
            self._import_animation_clip(clip_path)
            progress.setValue(idx * 3 + 1)

            core.bake_animation()
            progress.setValue(idx * 3 + 2)

            base_name = os.path.splitext(os.path.basename(clip_path))[0]
            output_path = self.output_folder + "/" + base_name
            ext = self.file_type_combo.currentText()

            if ext == ".fbx":
                output_path += ".fbx"
                cmds.file(rename=output_path)
                if self.export_selected_line.text():
                    cmds.select(self.export_selected_line.text(), replace=True)
                    maya.mel.eval('FBXExport -f "{}" -s'.format(output_path))
                else:
                    maya.mel.eval('FBXExport -f "{}"'.format(output_path))
            elif ext == ".ma":
                output_path += ".ma"
                cmds.file(rename=output_path)
                if self.export_selected_line.text():
                    cmds.select(self.export_selected_line.text(), replace=True)
                    cmds.file(exportSelected=True, type="mayaAscii")
                else:
                    cmds.file(exportAll=True, type="mayaAscii")

            progress.setValue(idx * 3 + 3)

            if os.path.exists(output_path):
                set_list_item_color(self.file_list_widget.item(idx), "lime")
                export_result.append("Successfully exported: " + output_path)
            else:
                set_list_item_color(self.file_list_widget.item(idx), "red")
                export_result.append("Failed exporting: " + output_path)

        print("------")
        for line in export_result:
            print(line)
        print("------")

        progress.setValue(num_ops)
        progress.close()

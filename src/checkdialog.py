from PyQt5.QtCore import Qt
from PyQt5.Qt import (
    QListWidgetItem
)
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QVBoxLayout,
)

from aqt.utils import (
    saveGeom, 
    restoreGeom,
)

dialogname = "addon_download_delayer_addon_selector"


class CheckDialog(QDialog):
    def __init__(self, parent=None, label1="", valuedict1=None, label2="", valuedict2=None, windowtitle=""):
        super().__init__(parent)
        if windowtitle:
            self.setWindowTitle(windowtitle)
        self.valuedict1 = valuedict1
        self.valuedict2 = valuedict2
        self.text_for_label1 = label1
        self.text_for_label2 = label2
        self.setupUI()
        restoreGeom(self, dialogname)

    def change_state(self, item):
        state = Qt.Checked if item.checkState() == Qt.Unchecked else Qt.Unchecked
        return item.setCheckState(state)

    def setupListWidget(self, indict):
        out = QListWidget()
        out.itemClicked.connect(lambda item: self.change_state(item))
        for text, state in indict.items():
            item = QListWidgetItem()
            item.setText(text)
            item.setCheckState(Qt.Checked if state else Qt.Unchecked)
            out.addItem(item)
        return out

    def setupUI(self):
        vlay = QVBoxLayout()
        label1 = QLabel(self.text_for_label1)
        label1.setWordWrap(True)
        self.listWidget1 = self.setupListWidget(self.valuedict1)
        label2 = QLabel(self.text_for_label2)
        label2.setWordWrap(True)
        self.listWidget2 = self.setupListWidget(self.valuedict2)
        buttonbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonbox.accepted.connect(self.onAccept)
        buttonbox.rejected.connect(self.onReject)
        vlay.addWidget(label1)
        vlay.addWidget(self.listWidget1)
        vlay.addWidget(label2)
        vlay.addWidget(self.listWidget2)
        vlay.addWidget(buttonbox)
        self.setLayout(vlay)

    def process_selection(self, widget, indict):
        for i in range(widget.count()):
            text = widget.item(i).text()
            indict[text] = True if widget.item(i).checkState() else False

    def onAccept(self):
        self.process_selection(self.listWidget1, self.valuedict1)
        self.process_selection(self.listWidget2, self.valuedict2)
        saveGeom(self, dialogname)
        self.accept()

    def onReject(self):
        saveGeom(self, dialogname)
        self.reject()

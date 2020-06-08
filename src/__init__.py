# Copyright: ijgnd
#            Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from concurrent.futures import Future
import datetime
from distutils.dir_util import copy_tree
from pprint import pprint as pp
import os
import shutil
import subprocess
import tempfile
from typing import Callable, Dict, List

from PyQt5 import QtCore

from anki.httpclient import HttpClient
from anki.hooks import wrap
from anki.lang import _
import aqt
from aqt.addons import (
    AddonsDialog,
    AddonManager,
    DownloadLogEntry,
    download_addons,
)
from aqt.qt import (
    QWidget,
)
from aqt.utils import askUser, showInfo


from .checkdialog import CheckDialog
from .config import (
    addons_pickle,
    gc,
)
from .file_load_save import (
    pickleload,
    picklesave,
)
from .known_creators import some_creators_and_their_addons


def invert_the_dict(d):
    out = {}
    for creator, addonlist in d.items():
        for aID in addonlist:
            out[aID] = creator
    return out
creator_for_nids = invert_the_dict(some_creators_and_their_addons)


today_candidates = {}
tempfolder = None


def date_fmted(epoch):
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def to_list_for_display(today_candidates, state, sort_by_name=True):
    if sort_by_name:
        temp = dict(sorted(today_candidates.items(), key=lambda x: x[1][1]))
    else:  # sort by reversed update date
        temp = dict(sorted(today_candidates.items(), key=lambda x: x[1][0], reverse=True))
    return {line: state for line in [vals[1] for vals in temp.values()]}


def process_gui_out(ids, previous_addons, gui_dict, source_dict):
    for label, state in gui_dict.items():
        for aID, vals in source_dict.items():
            if label == vals[1]:
                if state:
                    ids.append(aID)
                else:
                    previous_addons[aID] = [vals[0], label]
    return ids, previous_addons


def my_handle_update_info(
    parent: QWidget,
    mgr: AddonManager,
    client: HttpClient,
    items: List[Dict],
    on_done: Callable[[List[DownloadLogEntry]], None],
) -> None:
    global today_candidates
    today_candidates = {} # empty it in case I run updates twice in a row while the add-on manager window is open

    update_info = mgr.extract_update_info(items)
    mgr.update_supported_versions(update_info)

    updated_ids = mgr.updates_required(update_info)

    for f in updated_ids:
        for ui in update_info:
            if f == ui.id:
                stamp = ui.suitable_branch_last_modified
                creatorname = creator_for_nids.get(str(f), "")
                if creatorname:
                    creatorname += ", "
                lbl = f"{mgr.addonName(str(f))}  ({creatorname}{date_fmted(stamp)})"
                today_candidates[f] = [stamp, lbl]

    if not updated_ids:
        on_done([])
        return

    my_prompt_to_update(parent, mgr, client, updated_ids, on_done)
aqt.addons.handle_update_info = my_handle_update_info


def my_prompt_to_update(
    parent: QWidget,
    mgr: AddonManager,
    client: HttpClient,
    ids: List[int],
    on_done: Callable[[List[DownloadLogEntry]], None],
) -> None:
    global today_candidates
    global tempfolder

    previous_addons = pickleload(addons_pickle) # dict: id: [epoch, "string: addon-name (last update)"]
    if previous_addons:
        for aID, vals in previous_addons.items():
            if aID in today_candidates:
                if vals[0] == today_candidates[aID][0]:  # unchanged
                    del today_candidates[aID]

    l_1 = ("""<div>Updateable add-ons that have been <b>newly updated</b> since the last user prompt.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- The release date is listed in parentheses.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- This list is sorted by add-on name.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- Selected Add-ons will be updated.</div>"""
          )
    l_2 = ("""<div>Updateable add-ons that you <b>postponed the last time</b>.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- The release date is listed in parentheses.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- This list is sorted by the update date (in reversed order) which means the youngest update is on top.</div>"""
           """<div style="margin-left: 40px; margin-top: 0px;">- Selected Add-ons will be updated.</div>"""
          )
    d = CheckDialog(
        parent=None,
        label1=l_1,
        valuedict1=to_list_for_display(today_candidates, gc("default for updates since last check"), True),
        label2=l_2,
        valuedict2=to_list_for_display(previous_addons, False, False),
        windowtitle="Anki: Select add-ons to update",
    )
    if d.exec():
        ids = []
        new_previous_addons = {}
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.valuedict1, today_candidates)
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.valuedict2, previous_addons)
        picklesave(new_previous_addons, addons_pickle)

        if ids and gc("diff: ask the user about diffing"):
            msg = ("After downloading the new add-ons they are installed directly. But they are "
                   "only active after you restart Anki. This allows you to check/compare/diff the "
                   "newly downloaded versions before they are executed on your machine. To "
                   "do this this add-on can copy the current addon folder to a tempoary "
                   "folder and then call the diff program you set in the config. This will take "
                   "some time and requires sufficient free space on the partition that holds your "
                   "temp folder."
            )
            customfolder = gc("diff: instead of a temp folder use and overwrite this folder")
            if customfolder:
                msg += ("In the add-on config you've set a custom folder for the temporary copy "
                        "of the pre-update version of your add-ons. If this folder exists its "
                        "contents will be overwritten without any more questions." 
                        )
            else:
                msg += ("This add-on will not delete the temporary add-on folder later. "
                        "If you don't empty the add-on folder or if it's not emptied automatically this "
                        "addon will waste a lot of disk space in the long run. To avoid this problem "
                        "you can also set a 'permanent temp' folder in the add-on config that's always "
                        "overwritten."
                        )
            msg += "Click 'Yes' to copy and diff, 'No' to just download and install."
            if askUser(msg):
                aqt.mw.progress.start(immediate=True)
                if customfolder:
                    tempfolder = customfolder
                    # I originally had
                    #    shutil.rmtree(customfolder)
                    #    os.makedirs(customfolder)
                    # But in Windows 10 with 2.1.26 in 2020-06 I get
                    #      os.makedirs(customfolder)
                    #      File "os.py", line 221, in makedirs
                    #      PermissionError: [WinError 5] Access is denied: 'C:\\Users\\ijgnd\\Downloads\\addons21'
                    # But the permissions seem to be set correctly?
                    # So I manully create the folder outside of Anki and then never delete it.
                    for root, dirs, files in os.walk(customfolder):
                        for f in files:
                            os.unlink(os.path.join(root, f))
                        for d in dirs:
                            shutil.rmtree(os.path.join(root, d))
                else:
                    tempfolder = tempfile.mkdtemp()
                # shutil.copytree dirs_exist_ok is new in 3.8, 
                # shutil.copytree(aqt.mw.addonManager.addonsFolder(), tempfolder, dirs_exist_ok=True)
                copy_tree(aqt.mw.addonManager.addonsFolder(), tempfolder)               
                aqt.mw.progress.finish()
        download_addons(parent, mgr, ids, on_done, client)
aqt.addons.prompt_to_update = my_prompt_to_update


#def after_downloading(self, log: List[DownloadLogEntry]):
def do_diff_after_downloading(self, log: List[DownloadLogEntry]):
    global tempfolder

    if not tempfolder:
        return

    tool = gc("diff: command/program")
    args = gc("diff: command/programm parameters", [])
    argsstr = " ".join(args) if args else ""
    if gc("diff: block Anki by using subprocess.run"):
        sub_cmd = subprocess.run
    else:
        sub_cmd = subprocess.call
    shellcmd = " ".join([tool, argsstr, tempfolder, aqt.mw.addonManager.addonsFolder()])
    if gc("diff: run the command"):
        cmdlist = [tool, ]
        if args:
            cmdlist.extend(args)
        cmdlist.extend([tempfolder, aqt.mw.addonManager.addonsFolder()])
        sub_cmd(cmdlist)
    else:
        showInfo(shellcmd, title="Anki:diff command to run")
    tempfolder = None
AddonsDialog.after_downloading = wrap(AddonsDialog.after_downloading, do_diff_after_downloading)



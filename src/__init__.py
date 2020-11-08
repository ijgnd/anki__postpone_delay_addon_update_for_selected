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
from anki.utils import isWin
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
from aqt.utils import (
    askUser,
    showInfo,
    tooltip,
)


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
targetfolder = None


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
                    # store the latest upload date for postponed version of add-on 
                    # the dict previous_addons (if not empty) has this structure: 
                    # {id: [upload_time_epoch, name-with-humanreadable-format],}
                    # e.g.
                    # {1788670778: [1602825573, 'CrowdAnki JSON  (2020-10-16 07:19)'],   
                    #  1781298089: [1604760201, 'Searching PDF Reading (2020-11-07 15:43)']}
                    if (aID in previous_addons and (vals[0] > previous_addons[aID][0])) or aID not in previous_addons:
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
    # empty it in case I run updates twice in a row while the add-on manager window is open
    today_candidates = {}

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


def fmt(string_):
    return string_.replace("\n", " ").replace("DOUBLE", "\n\n").lstrip(" ").replace("\n\n ", "\n\n")


update_box_label_new_ones = ("""
<div>Updateable add-ons that have been <b>newly updated</b> since the last user prompt.</div>
<div style="margin-left: 40px; margin-top: 0px;">- The release date is listed in parentheses.</div>
<div style="margin-left: 40px; margin-top: 0px;">- This list is sorted by add-on name.</div>
<div style="margin-left: 40px; margin-top: 0px;">- Selected Add-ons will be updated.</div>
""")
update_box_label_already_postponed = ("""
<div>Updateable add-ons that you <b>postponed the last time</b>.</div>
<div style="margin-left: 40px; margin-top: 0px;">- The release date is listed in parentheses.</div>
<div style="margin-left: 40px; margin-top: 0px;">- This list is sorted by the update date
(in reversed order) which means the youngest update is on top.</div>
<div style="margin-left: 40px; margin-top: 0px;">- Selected Add-ons will be updated.</div>
""")


def sync_command(targetfolder):
    root = aqt.mw.addonManager.addonsFolder()
    if isWin:
        # for robocopy folders may not contain trailing slashes
        cmd = f'''robocopy "{root}" "{targetfolder}" /MIR'''
    else:
        # add trailing slash to source
        root = os.path.join(root, '')
        cmd = f'''rsync -a --delete "{root}" "{targetfolder}" '''
    if "\n" in cmd:
        return None
    return cmd


def diffmessage(synccmd):
    msg = fmt("""
After downloading the new add-ons they are installed directly. But they are
only active after you restart Anki. This allows you to check/compare/diff the
newly downloaded versions before they are executed on your machine.
DOUBLE
To do this this add-on can copy/sync the current addon folder to a temporary
folder and then call the diff program you set in the config.
DOUBLE
""")
    if gc("diff: instead of a temp folder use and overwrite this folder"):
        msg += fmt("""
In the add-on config you've set a custom folder for the temporary copy
of the pre-update version of your add-ons. If this folder exists its
contents will be overwritten without any more questions.
DOUBLE
""")
    else:
        msg += fmt("""
This add-on will not delete the temporary add-on folder later.
If you don't empty the add-on folder or if it's not emptied automatically this
addon will waste a lot of disk space in the long run. To avoid this problem
you can also set a 'permanent temp' folder in the add-on config that's always
overwritten.
DOUBLE
""")
    msg += fmt(f"""
This add-on will run the following command using the python subprocess module to 
sync the addons folder to the temporary folder. This command will also delete
files if necessary. Make sure to verify the following command before you continue. If you
don't understand the following command don't run this command. If there's an error in the
following command it might delete all your files - not just your Anki files but ALL files
on your computer! Use it at your own risk.
DOUBLE
{synccmd}
DOUBLE
"Click 'Yes' to copy and diff, 'No' to just download and install.
"""
    )

    return msg


def copy_old_versions_to_temp(synccmd):
    aqt.mw.progress.start(immediate=True)
    subprocess.run(synccmd, shell=True)
    aqt.mw.progress.finish()


def my_prompt_to_update(
    parent: QWidget,
    mgr: AddonManager,
    client: HttpClient,
    ids: List[int],
    on_done: Callable[[List[DownloadLogEntry]], None],
) -> None:
    global today_candidates
    global targetfolder

    previous_addons = pickleload(addons_pickle)  # dict: id: [epoch, "string: addon-name (last update)"]
    if previous_addons:
        # don't list versions as new that were already postponed
        for aID, vals in previous_addons.items():
            if aID in today_candidates:
                if vals[0] == today_candidates[aID][0]:  # unchanged
                    del today_candidates[aID]

    d = CheckDialog(
        parent=None,
        label1=update_box_label_new_ones,
        dict1=to_list_for_display(today_candidates, gc("default for updates since last check"), True),
        label2=update_box_label_already_postponed,
        dict2=to_list_for_display(previous_addons, False, False),
        windowtitle="Anki: Select add-ons to update",
    )
    if d.exec():
        ids = []
        new_previous_addons = {}
        # the dict new_previous_addons (if not empty) has this structure: 
        # {id: [upload_time_epoch, name-with-humanreadable-format],}
        # e.g.
        # {1788670778: [1602825573, 'CrowdAnki JSON  (2020-10-16 07:19)'],   
        #  1781298089: [1604760201, 'Searching PDF Reading (2020-11-07 15:43)']}
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.dict1, today_candidates)
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.dict2, previous_addons)
        picklesave(new_previous_addons, addons_pickle)

        if ids and gc("diff: ask the user about diffing"):
            targetfolder = gc("diff: instead of a temp folder use and overwrite this folder")
            if not targetfolder:
                targetfolder = tempfile.mkdtemp()
            if targetfolder.endswith("\\") and isWin:
                tooltip("adjust the config: folders in robosync may not end with a backlash.")
            else:
                synccmd = sync_command(targetfolder)
                if synccmd is None:
                    tooltip("The sync command to run may not contain linebreaks. Aborting ...")
                elif askUser(diffmessage(synccmd)):
                    copy_old_versions_to_temp(synccmd)
        download_addons(parent, mgr, ids, on_done, client)
aqt.addons.prompt_to_update = my_prompt_to_update


#def after_downloading(self, log: List[DownloadLogEntry]):
def do_diff_after_downloading(self, log: List[DownloadLogEntry]):
    global targetfolder

    if not targetfolder:
        return

    if not gc("diff: ask the user about diffing"):
        return

    tool = gc("diff: command/program")
    args = gc("diff: command/programm parameters", [])
    argsstr = " ".join(args) if args else ""
    
    env = os.environ.copy()
    toremove = ['LD_LIBRARY_PATH', 'QT_PLUGIN_PATH', 'QML2_IMPORT_PATH']
    for e in toremove:
        env.pop(e, None)
    
    if gc("diff: block Anki by using subprocess.run"):
        sub_cmd = subprocess.run
    else:
        sub_cmd = subprocess.Popen
    shellcmd = " ".join([tool, argsstr, targetfolder, aqt.mw.addonManager.addonsFolder()])
    if gc("diff: run the command"):
        cmdlist = [tool, ]
        if args:
            for a in args:  # handle e.g. [""]
                if a and isinstance(a, str):
                    cmdlist.append(a)
        cmdlist.extend([targetfolder, aqt.mw.addonManager.addonsFolder()])
        sub_cmd(cmdlist, env=env)
    else:
        showInfo(shellcmd, title="Anki:diff command to run")
    targetfolder = None
AddonsDialog.after_downloading = wrap(AddonsDialog.after_downloading, do_diff_after_downloading)

# Copyright: ijgnd
#            Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from concurrent.futures import Future
import datetime
from pprint import pprint as pp
from typing import Callable, Dict, List

from PyQt5 import QtCore

from anki.httpclient import HttpClient
from anki.hooks import wrap
from anki.lang import _
import aqt
from aqt.addons import (
    AddonManager,
    DownloadLogEntry,
    download_addons,
)
from aqt.qt import (
    QWidget,
)
from aqt.utils import askUser


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



def date_fmted(epoch):
    return datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def to_list_for_display(today_candidates, state):
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

    previous_addons = pickleload(addons_pickle) # dict: id: [epoch, "string: addon-name (last update)"]
    if previous_addons:
        for aID, vals in previous_addons.items():
            if aID in today_candidates:
                if vals[0] == today_candidates[aID][0]:  # unchanged
                    del today_candidates[aID]

    l_1 = ("Updateable add-ons that have been <b>newly updated</b> since the last user prompt.<br>"
           "Selected Add-ons will be updated.<br>"
           "The release date is listed in parentheses."
          )
    l_2 = ("Updateable add-ons that you posponed the last time<br>"
           "Selected Add-ons will be updated."
          )
    d = CheckDialog(
        parent=None,
        label1=l_1,
        valuedict1=to_list_for_display(today_candidates, gc("default for updates since last check")),
        label2=l_2,
        valuedict2=to_list_for_display(previous_addons, False),
        windowtitle="Anki: Select add-ons to update",
    )
    if d.exec():
        ids = []
        new_previous_addons = {}
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.valuedict1, today_candidates)
        ids, new_previous_addons = process_gui_out(ids, new_previous_addons, d.valuedict2, previous_addons)
        picklesave(new_previous_addons, addons_pickle)

        download_addons(parent, mgr, ids, on_done, client)
aqt.addons.prompt_to_update = my_prompt_to_update

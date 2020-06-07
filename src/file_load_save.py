import os
import pickle

from .config import user_files_folder


def pickleload(thefile):
    if os.path.isfile(thefile):
        with open(thefile, 'rb') as PO:
            try:
                out = pickle.load(PO)
            except:
                out = {}
    else:
        out = {}
    return out


def picklesave(var, thefile):
    # prevent error after deleting add-on
    if os.path.exists(user_files_folder):
        with open(thefile, 'wb') as PO:
            pickle.dump(var, PO)

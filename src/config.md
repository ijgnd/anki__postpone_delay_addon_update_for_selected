### config options

- `"diff: command/program"`: backslashes need to be escaped. So in Windows you would e.g. set 
`"C:\\Program Files\\WinMerge\\WinMergeU.exe"`.
- `"diff: command/programm parameters"` is a list. For WinMerge I use `["/r"]` so that in WinMerge
I can switch "View > Tree Mode" to hide identical folders.
- `"diff: instead of a temp folder use and overwrite this folder"` if "false" python creates
a temporary folder using the tempfile module. If this is set to a path this path is used. Note to self:
In Windows I got a PermissionError when trying to create this folder. So I created it outside of
Anki.

### about diff

Anki has its own python interpreter. When I try to open some external programs from within
Anki I sometimes run into problems. 

For Meld I get

    Fatal Python error: init_fs_encoding: failed to get the Python codec of the filesystem encoding
    Python runtime state: core initialized
    ModuleNotFoundError: No module named 'encodings'
    Current thread 0x00007f262ddb8740 (most recent call first):
    <no Python frame>

For kdiff3/kompare I get

    kdiff3: ankipath/bin/libQt5Core.so.5: version `Qt_5.13.2_PRIVATE_API' not found (required by /lib64/libKF5XmlGui.so.5)
    kdiff3: ankipath/bin/libQt5Core.so.5: version `Qt_5.13.2_PRIVATE_API' not found (required by /lib64/libQt5Xml.so.5)
    kdiff3: ankipath/bin/libQt5Core.so.5: version `Qt_5.13.2_PRIVATE_API' not found (required by /lib64/libQt5TextToSpeech.so.5)
    qt: QXcbConnection: XCB error: 3 (BadWindow), sequence: 3403, resource id: 42238171, major code: 40 (TranslateCoords), minor code: 0

Finding out why this happens is inefficient for me. If you have a fix please let me know.

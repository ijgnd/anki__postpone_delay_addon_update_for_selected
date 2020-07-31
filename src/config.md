### config options

- `"diff: command/program"`: backslashes need to be escaped. So in Windows you would e.g. set 
`"C:\\Program Files\\WinMerge\\WinMergeU.exe"`.
- `"diff: command/programm parameters"` is a list. For WinMerge I use `["/r"]` so that in WinMerge
I can switch "View > Tree Mode" to hide identical folders.
- `"diff: instead of a temp folder use and overwrite this folder"` if "false" python creates
a temporary folder using the tempfile module. If this is set to a path this path is used. Note to self:
In Windows I got a PermissionError when trying to create this folder. So I created it outside of
Anki.

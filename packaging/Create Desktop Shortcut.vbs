Option Explicit
Dim shell, files, folder, executable, shortcut
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
folder = files.GetParentFolderName(WScript.ScriptFullName)
executable = files.BuildPath(folder, "SpeedEditorCustomizer.exe")
If Not files.FileExists(executable) Then
    MsgBox "Extract the entire ZIP first, then run this file from beside SpeedEditorCustomizer.exe.", 48, "Speed Editor Customizer"
    WScript.Quit 1
End If
On Error Resume Next
Set shortcut = shell.CreateShortcut(shell.SpecialFolders("Desktop") & "\Speed Editor Customizer.lnk")
shortcut.TargetPath = executable
shortcut.WorkingDirectory = folder
shortcut.IconLocation = executable & ",0"
shortcut.Description = "Open Speed Editor Customizer"
shortcut.Save
If Err.Number <> 0 Then
    MsgBox "Could not create the shortcut: " & Err.Description, 48, "Speed Editor Customizer"
    WScript.Quit 1
End If
On Error GoTo 0
MsgBox "Desktop shortcut created. Keep this app folder in its current location so the shortcut continues to work.", 64, "Speed Editor Customizer"

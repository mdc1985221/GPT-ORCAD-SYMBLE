$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$pythonTarget = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\pythonw.exe'
$launcher = Join-Path $PSScriptRoot 'launcher.py'
if (-not (Test-Path -LiteralPath $pythonTarget)) { throw 'Python runtime is missing' }
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Launcher is missing' }
$desktopFolder = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopFolder 'Cadence器件助手-Git版.lnk'
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonTarget
$shortcut.Arguments = '"' + $launcher + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'Cadence 器件助手：启动当前源码版，原理符号、PCB、3D 与器件库'
$iconTarget = Join-Path $projectRoot 'EXE\CadenceAssistant-20261118\CadenceAssistant.exe'
if (Test-Path -LiteralPath $iconTarget) { $shortcut.IconLocation = "$iconTarget,0" }
$shortcut.Save()
$verify = $shortcutShell.CreateShortcut($shortcutPath)
if ($verify.TargetPath -ne $pythonTarget -or $verify.Arguments -ne ('"' + $launcher + '"') -or $verify.WorkingDirectory -ne $projectRoot) { throw 'Shortcut verification failed' }
Write-Output "Updated and verified: $shortcutPath"

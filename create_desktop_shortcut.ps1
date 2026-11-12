# Puts a "KaupBudget" icon on your desktop. Re-run it if you move the app folder.
$appDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path $desktop "KaupBudget.lnk"))
$lnk.TargetPath = Join-Path $appDir "KaupBudget.bat"
$lnk.WorkingDirectory = $appDir
$lnk.WindowStyle = 7   # start minimized so the setup console stays out of the way
$icon = Join-Path $appDir "kaupbudget\static\icon.ico"
if (Test-Path $icon) { $lnk.IconLocation = $icon }
$lnk.Description = "KaupBudget"
$lnk.Save()
Write-Host "Shortcut created on your desktop."

<#
.SYNOPSIS
  Build any single-app handheld OS (ChessOS by default) and put it on an SD card. Windows 10/11.

.DESCRIPTION
  The app the handheld boots into is set in appliance.json (see "use" / "new-app").

  .\setup.ps1 deploy             guided: build + put the OS or the app on an SD card   <- start here
  .\setup.ps1 setup              create .venv and install the PC build tools
  .\setup.ps1 build              app assets (device\<app>\build.ps1), boot logo -> dist\
  .\setup.ps1 run                run the app on this PC (keyboard)
  .\setup.ps1 test               start the app, take screenshots, check it didn't crash
  .\setup.ps1 image              download ArkOS-K36 and build work\<app>.img (needs WSL)
  .\setup.ps1 flash -Disk N      write work\<app>.img to SD card disk N (erases it, admin prompt)
  .\setup.ps1 update -Disk N     refresh the app on a card made by 'flash', keeps its data (admin prompt)
  .\setup.ps1 install -Drive G   add the app to an existing ArkOS card's Ports menu (EASYROMS drive)
  .\setup.ps1 repair             fix BOOT/EASYROMS after the handheld lost power (chkdsk, admin prompt)
  .\setup.ps1 new-app -Name noteos -Title NoteOS [-Template python-sdl|native]
  .\setup.ps1 use -Name chessos  switch the active app
  .\setup.ps1 ttsbench -Drive G  copy the text-to-speech benchmark port to EASYROMS
  .\setup.ps1 all                setup + build + image

  Options: -WorkDir <path>  big files (~20 GB free needed), default .\work
           -Panel <1-7>     use another ArkOS-K36 screen file (black screen? try this)
#>
param(
  [Parameter(Position = 0)][ValidateSet("deploy", "setup", "build", "run", "test", "image", "flash", "update", "install",
                                        "repair", "new-app", "use", "ttsbench", "all", "help")]
  [string]$Command = "help",
  [int]$Disk = -1,
  [string]$WorkDir = "$PSScriptRoot\work",
  [int]$Panel = 0,
  [string]$Drive = "",
  [string]$Name = "",
  [string]$Title = "",
  [ValidateSet("python-sdl", "native")][string]$Template = "python-sdl"
)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$ArkUrl = "https://github.com/AeolusUX/ArkOS-K36/releases/download/ArkOS.K36.08112025/ArkOS_K36_v2.0_08112025.img.xz"
$ArkXzSize = 2061962728

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Green }
function Need-Venv { if (-not (Test-Path $Py)) { throw "Run '.\setup.ps1 setup' first." } }
function Run-Py { & $Py @args; if ($LASTEXITCODE -ne 0) { throw "python $($args[0]) failed" } }
function To-Wsl($p) { (& wsl.exe -e wslpath -a ($p -replace '\\', '/')).Trim() }
function Cfg { Get-Content (Join-Path $Root "appliance.json") -Raw | ConvertFrom-Json }
function App-Dir { Join-Path $Root ("device\" + (Cfg).app) }
function Dist-Ready { $a = (Cfg).app; (Test-Path "$Root\dist\EASYROMS\ports\$a\main.py") -or (Test-Path "$Root\dist\EASYROMS\ports\$a\start") }
function Image-Path { Join-Path $WorkDir ((Cfg).app + ".img") }

function Do-Setup {
  Step "Python virtual environment"
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.9+ from python.org first." }
  if (-not (Test-Path $Py)) { python -m venv (Join-Path $Root ".venv") }
  & $Py -m pip install -q --upgrade pip
  & $Py -m pip install -q -r (Join-Path $Root "requirements-dev.txt")
  Step "Checking WSL (only needed for 'image' and 'update')"
  if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    & wsl.exe -e sh -c "command -v debugfs >/dev/null || command -v /usr/sbin/debugfs >/dev/null && echo '  WSL + debugfs OK' || echo '  WSL found, but run: sudo apt install e2fsprogs dosfstools python3-venv'"
  } else {
    Write-Host "  WSL not found. 'build', 'run' and 'install' work without it; 'image' and 'update' need it (wsl --install)."
  }
}

function Do-Build {
  Need-Venv
  $c = Cfg
  Step "Building $($c.title) (device\$($c.app))"
  $hook = Join-Path (App-Dir) "build.ps1"
  if (Test-Path $hook) { . $hook }   # the app's own asset steps
  Step "Boot logo"
  Run-Py "$Root\tools\build_bootlogo.py"
  Step "dist\ (files for the SD card)"
  Get-ChildItem "$Root\device" -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
  Run-Py "$Root\tools\build_dist.py"
}

function Do-Run {
  Need-Venv
  $dir = App-Dir
  Push-Location $dir
  try {
    if (Test-Path "$dir\main.py") { & $Py main.py } else { throw "No main.py: native apps run on the device only." }
  } finally { Pop-Location }
}

function Do-Test {
  # Start the app, press A once, save screenshots, quit. Fails if it crashed.
  Need-Venv
  $out = Join-Path $Root "build\smoke"
  Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force "$out\shots" | Out-Null
  $env:CHESSOS_SCALE = "1"; $env:CHESSOS_SAVE = "$out\save.json"; $env:CHESSOS_SHOTS = "$out\shots"
  $env:CHESSOS_AUTOPILOT = "3.2|shot:start|a|0.6|a|1.4|shot:after|start|0.5|shot:menu|quit"
  Push-Location (App-Dir)
  try { & $Py main.py } finally {
    Pop-Location
    Remove-Item Env:CHESSOS_AUTOPILOT, Env:CHESSOS_SCALE, Env:CHESSOS_SAVE, Env:CHESSOS_SHOTS
  }
  if (Test-Path (Join-Path (App-Dir) "crash.log")) { throw "the app crashed - see crash.log" }
  $shots = Get-ChildItem "$out\shots\*.bmp"
  if ($shots.Count -lt 3) { throw "smoke test failed: only $($shots.Count) of 3 screenshots" }
  Write-Host "Smoke test passed: $($shots.Count) screenshots in $out\shots"
}

function Do-Image {
  Need-Venv
  if (-not (Dist-Ready)) { Do-Build }
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  $xz = Join-Path $WorkDir "ArkOS_K36_v2.0_08112025.img.xz"
  if (-not (Test-Path $xz) -or (Get-Item $xz).Length -ne $ArkXzSize) {
    Step "Downloading ArkOS-K36 (2 GB, community ArkOS build for K36/R36S clones)"
    & curl.exe -L --fail -o $xz $ArkUrl
    if ((Get-Item $xz).Length -ne $ArkXzSize) { throw "download incomplete" }
  }
  $wWork = To-Wsl $WorkDir
  $wRoot = To-Wsl $Root
  if (-not (Test-Path (Join-Path $WorkDir "arkos.img"))) {
    Step "Decompressing (9 GB)"
    & wsl.exe -e sh -c "xz -dkc '$wWork/ArkOS_K36_v2.0_08112025.img.xz' > '$wWork/arkos.img'"
  }
  Step "Building the $((Cfg).title) image"
  $panelEnv = if ($Panel -gt 0) { "PANEL=$Panel " } else { "" }
  & wsl.exe -e bash -c "$panelEnv bash '$wRoot/tools/image/build_image.sh' '$wWork' '$wRoot'"
  if ($LASTEXITCODE -ne 0) { throw "image build failed" }
  Write-Host "`nImage ready: $(Image-Path)  ->  .\setup.ps1 flash -Disk <number>"
}

function Show-Disks {
  Get-Disk | Format-Table Number, FriendlyName, BusType, @{n = "GB"; e = { [math]::Round($_.Size / 1GB, 1) } }, IsBoot, IsSystem -AutoSize | Out-Host
}

function Confirm-Card($verb) {
  if ($Disk -lt 0) { Show-Disks; throw "Pick the SD card from the list above:  .\setup.ps1 $Command -Disk <Number>" }
  $d = Get-Disk -Number $Disk
  if ($d.IsBoot -or $d.IsSystem -or $d.BusType -notin @("USB", "SD", "MMC")) { throw "Disk $Disk is not a removable USB/SD card." }
  Write-Host ("`nDisk {0}: {1}, {2} GB, {3}" -f $Disk, $d.FriendlyName, [math]::Round($d.Size / 1GB, 1), $d.BusType) -ForegroundColor Yellow
  Write-Host $verb -ForegroundColor Yellow
  $ans = Read-Host "Type the disk number again to continue"
  if ($ans -ne "$Disk") { Write-Host "Cancelled."; return $null }
  return $d
}

function Do-Flash {
  Need-Venv
  $img = Image-Path
  if (-not (Test-Path $img)) { throw "No image yet. Run '.\setup.ps1 image' first." }
  $d = Confirm-Card "EVERYTHING on this card will be erased."
  if (-not $d) { return }
  $log = Join-Path $WorkDir "flash.log"
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_write.ps1`" -Disk $Disk -ExpectedSize $($d.Size) -Image `"$img`" -Log `"$log`" -Python `"$Py`""
  Step "Writing (admin prompt). This takes 5-15 minutes."
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $argList
  Get-Content $log | Select-String "Target|OK:|ERROR|DONE|VERIFY"
  Write-Host "First boot takes a few minutes (ArkOS sets up EASYROMS and reboots). Don't switch off."
}

function Do-Update {
  Need-Venv
  if (-not (Dist-Ready)) { Do-Build }
  $d = Confirm-Card "$((Cfg).title) will be (re)installed in /opt on this card. Its other data is kept."
  if (-not $d) { return }
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  $log = Join-Path $WorkDir "update.log"
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_update.ps1`" -Disk $Disk -ExpectedSize $($d.Size) -WorkDir `"$WorkDir`" -Log `"$log`" -Python `"$Py`""
  Step "Updating (admin prompt). About 5 minutes."
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $argList
  Get-Content $log | Select-String "1/3|2/3|3/3|OK|app:|removing|files|filesystem|ERROR|DONE"
}

function Find-Easyroms {
  if ($Drive) { return $Drive.TrimEnd(':') }
  $v = Get-Volume | Where-Object { $_.FileSystemLabel -eq "EASYROMS" -and $_.DriveLetter } | Select-Object -First 1
  if (-not $v) { throw "No EASYROMS drive found. Insert an ArkOS card, or pass -Drive <letter>." }
  return [string]$v.DriveLetter
}

function Do-Install {
  # "App only": add the app to an existing ArkOS card as a Ports entry (no reflash, no admin).
  if (-not (Dist-Ready)) { Do-Build }
  $c = Cfg
  $letter = Find-Easyroms
  $ports = "${letter}:\ports"
  if (-not (Test-Path $ports)) { throw "$ports not found - is ${letter}: the EASYROMS drive?" }
  Step "Copying $($c.title) to $ports"
  & robocopy.exe "$Root\dist\EASYROMS\ports" $ports /E /R:2 /W:2 /NFL /NDL /NP /NJH /NJS | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "copy failed (robocopy $LASTEXITCODE) - try '.\setup.ps1 repair'" }
  try { Write-VolumeCache -DriveLetter $letter } catch {}
  Write-Host "Done. On the handheld: Ports > $($c.title).  Optional: Ports > '$($c.title) Boot Mode' starts it on every boot."
}

function Do-Repair {
  $log = Join-Path $WorkDir "repair.log"
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  Step "Repairing BOOT and EASYROMS (admin prompt)"
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_repair.ps1`" -Log `"$log`""
  Get-Content $log | Select-String "before|after|not found"
}

function Do-NewApp {
  Need-Venv
  if (-not $Name -or -not $Title) { throw "Usage: .\setup.ps1 new-app -Name noteos -Title NoteOS [-Template python-sdl|native]" }
  Run-Py "$Root\tools\new_app.py" $Name $Title --template $Template
  Write-Host "Next: edit device\$Name\, then .\setup.ps1 run  (or deploy)"
}

function Do-Use {
  Need-Venv
  if (-not $Name) {
    Get-ChildItem "$Root\device" -Directory | Where-Object { Test-Path "$($_.FullName)\app.json" } | ForEach-Object { "  " + $_.Name }
    throw "Usage: .\setup.ps1 use -Name <one of the apps above>"
  }
  Run-Py "$Root\tools\new_app.py" --use $Name
}

function Do-Deploy {
  # Guided: pick the app, build it, then put it on a card in one of three ways.
  Need-Venv
  $c = Cfg
  $apps = @(Get-ChildItem "$Root\device" -Directory | Where-Object { Test-Path "$($_.FullName)\app.json" } | ForEach-Object { $_.Name })
  Write-Host "`nActive app: $($c.title) ($($c.app))    available: $($apps -join ', ')" -ForegroundColor Cyan
  $pick = Read-Host "Press Enter to keep it, or type another app name"
  if ($pick) { $script:Name = $pick; Do-Use; $c = Cfg }
  Write-Host @"

How should $($c.title) get onto the SD card?
  1) Whole OS - erase a card and make it boot straight into $($c.title)   (needs WSL, admin prompt)
  2) App only - add $($c.title) to a card that already runs ArkOS          (Ports menu, no reflash)
  3) Update   - refresh $($c.title) on a card made with option 1           (keeps its data, admin prompt)
"@
  $mode = Read-Host "Choose 1, 2 or 3"
  Do-Build
  switch ($mode) {
    "1" { Do-Image; Show-Disks; $script:Disk = [int](Read-Host "Disk number of the SD card"); Do-Flash }
    "2" { Do-Install }
    "3" { Show-Disks; $script:Disk = [int](Read-Host "Disk number of the SD card"); Do-Update }
    default { Write-Host "Nothing done." }
  }
}

function Do-TtsBench {
  # Build the R36S text-to-speech benchmark port and copy it to the card's EASYROMS drive.
  $letter = Find-Easyroms
  $dl = Join-Path $WorkDir "tts"
  New-Item -ItemType Directory -Force $dl | Out-Null
  $wDl = To-Wsl $dl; $wRoot = To-Wsl $Root
  Step "Downloading Piper, Supertonic and Python 3.7 aarch64 packages"
  & wsl.exe -e bash "$wRoot/tools/tts/fetch.sh" $wDl
  Step "Converting Supertonic for onnxruntime 1.14 and verifying identical output"
  & wsl.exe -e bash "$wRoot/tools/tts/verify_downgrade.sh" $wDl $wRoot
  Step "Packaging"
  & wsl.exe -e bash "$wRoot/tools/tts/package.sh" $wDl $wRoot "$wDl/pkg"
  Step "Copying to ${letter}:\ports"
  & robocopy.exe "$dl\pkg" "${letter}:\ports" /E /R:2 /W:2 /NFL /NDL /NP /NJH /NJS | Out-Null
  Write-Host "Done. On the handheld: Ports > TTS Benchmark"
}

switch ($Command) {
  "deploy" { Do-Deploy }
  "setup" { Do-Setup }
  "build" { Do-Build }
  "run" { Do-Run }
  "test" { Do-Test }
  "image" { Do-Image }
  "flash" { Do-Flash }
  "update" { Do-Update }
  "install" { Do-Install }
  "repair" { Do-Repair }
  "new-app" { Do-NewApp }
  "use" { Do-Use }
  "ttsbench" { Do-TtsBench }
  "all" { Do-Setup; Do-Build; Do-Image }
  default { Get-Help $PSCommandPath -Detailed | Out-String | Write-Host }
}

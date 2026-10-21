<#
.SYNOPSIS
  ChessOS build & flash helper (Windows 10/11).

.DESCRIPTION
  .\setup.ps1 setup            create .venv and install the PC build tools
  .\setup.ps1 build            puzzles, sprites, voice, sfx, boot logo -> dist\
  .\setup.ps1 run              play ChessOS on this PC (keyboard)
  .\setup.ps1 test             quick automated smoke test with screenshots
  .\setup.ps1 image            download ArkOS-K36 and build work\chessos.img (needs WSL)
  .\setup.ps1 flash -Disk N    write work\chessos.img to SD card disk N (admin prompt)
  .\setup.ps1 all              setup + build + image

  Options: -WorkDir <path>  big files (~20 GB free needed), default .\work
           -Panel <1-7>     use another ArkOS-K36 screen file (black screen? try this)
#>
param(
  [Parameter(Position = 0)][ValidateSet("setup", "build", "run", "test", "image", "flash", "all", "help")]
  [string]$Command = "help",
  [int]$Disk = -1,
  [string]$WorkDir = "$PSScriptRoot\work",
  [int]$Panel = 0
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

function Do-Setup {
  Step "Python virtual environment"
  if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw "Install Python 3.9+ from python.org first." }
  if (-not (Test-Path $Py)) { python -m venv (Join-Path $Root ".venv") }
  & $Py -m pip install -q --upgrade pip
  & $Py -m pip install -q -r (Join-Path $Root "requirements-dev.txt")
  Step "Checking WSL (only needed for 'image')"
  if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
    & wsl.exe -e sh -c "command -v debugfs >/dev/null || command -v /usr/sbin/debugfs >/dev/null && echo '  WSL + debugfs OK' || echo '  WSL found, but run: sudo apt install e2fsprogs dosfstools python3-venv'"
  } else {
    Write-Host "  WSL not found. 'build' and 'run' work without it; 'image' needs it (wsl --install)."
  }
}

function Do-Build {
  Need-Venv
  Step "Puzzle packs (Lichess puzzle database, CC0)"
  Run-Py "$Root\tools\build_puzzles.py"
  Step "Sprites"
  Run-Py "$Root\tools\build_assets.py"
  Step "Voice clips + sound effects (Windows speech)"
  Run-Py "$Root\tools\build_audio.py"
  Step "Boot logo"
  Run-Py "$Root\tools\build_bootlogo.py"
  Step "dist\ (files for the SD card)"
  Get-ChildItem "$Root\device" -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
  Run-Py "$Root\tools\build_dist.py"
}

function Do-Test {
  # Scripted run: opens the first lesson, solves nothing, saves screenshots.
  Need-Venv
  $out = Join-Path $Root "build\smoke"
  Remove-Item -Recurse -Force $out -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Force "$out\shots" | Out-Null
  $env:CHESSOS_SCALE = "1"; $env:CHESSOS_SAVE = "$out\save.json"; $env:CHESSOS_SHOTS = "$out\shots"
  $env:CHESSOS_AUTOPILOT = "3.2|shot:home|a|0.6|a|1.4|shot:intro|a|1.6|shot:lesson|start|0.5|shot:pause|quit"
  Push-Location "$Root\device\chessos"
  try { & $Py main.py } finally {
    Pop-Location
    Remove-Item Env:CHESSOS_AUTOPILOT, Env:CHESSOS_SCALE, Env:CHESSOS_SAVE, Env:CHESSOS_SHOTS
  }
  $shots = Get-ChildItem "$out\shots\*.bmp"
  if ($shots.Count -lt 4) { throw "smoke test failed: only $($shots.Count) of 4 screenshots" }
  Write-Host "Smoke test passed: $($shots.Count) screenshots in $out\shots"
}

function Do-Image {
  Need-Venv
  if (-not (Test-Path "$Root\dist\EASYROMS\ports\chessos\main.py")) { Do-Build }
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
  Step "Building ChessOS image"
  $panelEnv = if ($Panel -gt 0) { "PANEL=$Panel " } else { "" }
  & wsl.exe -e bash -c "$panelEnv bash '$wRoot/tools/image/build_image.sh' '$wWork' '$wRoot'"
  if ($LASTEXITCODE -ne 0) { throw "image build failed" }
  Write-Host "`nImage ready: $WorkDir\chessos.img  ->  .\setup.ps1 flash -Disk <number>"
}

function Do-Flash {
  Need-Venv
  $img = Join-Path $WorkDir "chessos.img"
  if (-not (Test-Path $img)) { throw "No image yet. Run '.\setup.ps1 image' first." }
  if ($Disk -lt 0) {
    Get-Disk | Format-Table Number, FriendlyName, BusType, @{n = "GB"; e = { [math]::Round($_.Size / 1GB, 1) } }, IsBoot, IsSystem -AutoSize
    throw "Pick the SD card from the list above:  .\setup.ps1 flash -Disk <Number>"
  }
  $d = Get-Disk -Number $Disk
  if ($d.IsBoot -or $d.IsSystem -or $d.BusType -notin @("USB", "SD", "MMC")) { throw "Disk $Disk is not a removable USB/SD card." }
  Write-Host ("`nDisk {0}: {1}, {2} GB, {3}" -f $Disk, $d.FriendlyName, [math]::Round($d.Size / 1GB, 1), $d.BusType) -ForegroundColor Yellow
  Write-Host "EVERYTHING on this card will be erased." -ForegroundColor Yellow
  $ans = Read-Host "Type the disk number again to continue"
  if ($ans -ne "$Disk") { Write-Host "Cancelled."; return }
  $log = Join-Path $WorkDir "flash.log"
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_write.ps1`" -Disk $Disk -ExpectedSize $($d.Size) -Image `"$img`" -Log `"$log`" -Python `"$Py`""
  Step "Writing (admin prompt). This takes 5-15 minutes."
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $argList
  Get-Content $log | Select-String "Target|OK:|ERROR|DONE|VERIFY"
}

switch ($Command) {
  "setup" { Do-Setup }
  "build" { Do-Build }
  "run" { Need-Venv; Push-Location "$Root\device\chessos"; try { & $Py main.py } finally { Pop-Location } }
  "test" { Do-Test }
  "image" { Do-Image }
  "flash" { Do-Flash }
  "all" { Do-Setup; Do-Build; Do-Image }
  default { Get-Help $PSCommandPath -Detailed | Out-String | Write-Host }
}

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
  .\setup.ps1 update -Disk N   refresh ChessOS on an already-flashed card, keeps progress (admin prompt)
  .\setup.ps1 repair           fix BOOT/EASYROMS after the handheld lost power (chkdsk, admin prompt)
  .\setup.ps1 ttsbench -Drive G   copy the text-to-speech benchmark port to EASYROMS (drive G:)
  .\setup.ps1 all              setup + build + image

  Options: -WorkDir <path>  big files (~20 GB free needed), default .\work
           -Panel <1-7>     use another ArkOS-K36 screen file (black screen? try this)
#>
param(
  [Parameter(Position = 0)][ValidateSet("setup", "build", "run", "test", "image", "flash", "update", "repair", "ttsbench", "all", "help")]
  [string]$Command = "help",
  [int]$Disk = -1,
  [string]$WorkDir = "$PSScriptRoot\work",
  [int]$Panel = 0,
  [string]$Drive = ""
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
  Step "Voice clips (Kokoro, Apache-2.0) + sound effects"
  # The repo ships finished clips; Kokoro is only downloaded when clips must be (re)made.
  if (-not (Test-Path "$Root\device\chessos\assets\voice\engine.txt") -or $env:CHESSOS_TTS -eq "kokoro") {
    $kdir = Join-Path $WorkDir "kokoro"
    New-Item -ItemType Directory -Force $kdir | Out-Null
    foreach ($f in "kokoro-v1.0.onnx", "voices-v1.0.bin") {
      if (-not (Test-Path "$kdir\$f")) {
        Write-Host "  downloading $f"
        & curl.exe -L --fail -s -o "$kdir\$f" "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/$f"
      }
    }
    $env:CHESSOS_KOKORO_DIR = $kdir
  }
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

function Confirm-Card {
  if ($Disk -lt 0) {
    Get-Disk | Format-Table Number, FriendlyName, BusType, @{n = "GB"; e = { [math]::Round($_.Size / 1GB, 1) } }, IsBoot, IsSystem -AutoSize
    throw "Pick the SD card from the list above:  .\setup.ps1 $Command -Disk <Number>"
  }
  $d = Get-Disk -Number $Disk
  if ($d.IsBoot -or $d.IsSystem -or $d.BusType -notin @("USB", "SD", "MMC")) { throw "Disk $Disk is not a removable USB/SD card." }
  Write-Host ("`nDisk {0}: {1}, {2} GB, {3}" -f $Disk, $d.FriendlyName, [math]::Round($d.Size / 1GB, 1), $d.BusType) -ForegroundColor Yellow
  return $d
}

function Do-Update {
  # Refresh ChessOS on a card that was flashed with 'image'/'flash' (keeps your progress).
  Need-Venv
  if (-not (Test-Path "$Root\dist\EASYROMS\ports\chessos\main.py")) { Do-Build }
  $d = Confirm-Card
  $ans = Read-Host "Update ChessOS on this card? Type the disk number again"
  if ($ans -ne "$Disk") { Write-Host "Cancelled."; return }
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  $log = Join-Path $WorkDir "update.log"
  $argList = "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_update.ps1`" -Disk $Disk -ExpectedSize $($d.Size) -WorkDir `"$WorkDir`" -Log `"$log`" -Python `"$Py`""
  Step "Updating (admin prompt). About 5 minutes."
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList $argList
  Get-Content $log | Select-String "1/3|2/3|3/3|OK|files|filesystem|ERROR|DONE"
}

function Do-TtsBench {
  # Build the R36S text-to-speech benchmark port and copy it to the card's EASYROMS drive.
  if (-not $Drive) { throw "Give the EASYROMS drive letter:  .\setup.ps1 ttsbench -Drive G" }
  $dl = Join-Path $WorkDir "tts"
  New-Item -ItemType Directory -Force $dl | Out-Null
  $wDl = To-Wsl $dl; $wRoot = To-Wsl $Root
  Step "Downloading Piper, Supertonic and Python 3.7 aarch64 packages"
  & wsl.exe -e bash "$wRoot/tools/tts/fetch.sh" $wDl
  Step "Converting Supertonic for onnxruntime 1.14 and verifying identical output"
  & wsl.exe -e bash "$wRoot/tools/tts/verify_downgrade.sh" $wDl $wRoot
  Step "Packaging"
  & wsl.exe -e bash "$wRoot/tools/tts/package.sh" $wDl $wRoot "$wDl/pkg"
  $ports = "$($Drive.TrimEnd(':')):\ports"
  if (-not (Test-Path $ports)) { throw "$ports not found - is $Drive the EASYROMS drive?" }
  Step "Copying to $ports"
  robocopy "$dl\pkg" $ports /E /NFL /NDL /NP /NJH /NJS | Out-Null
  Write-Host "Done. On the R36S: START > Power > ArkOS menus > Ports > TTS Benchmark"
}

function Do-Repair {
  $log = Join-Path $WorkDir "repair.log"
  New-Item -ItemType Directory -Force $WorkDir | Out-Null
  Step "Repairing BOOT and EASYROMS (admin prompt)"
  Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$Root\tools\card_repair.ps1`" -Log `"$log`""
  Get-Content $log | Select-String "before|after|not found"
}

switch ($Command) {
  "repair" { Do-Repair }
  "update" { Do-Update }
  "ttsbench" { Do-TtsBench }
  "setup" { Do-Setup }
  "build" { Do-Build }
  "run" { Need-Venv; Push-Location "$Root\device\chessos"; try { & $Py main.py } finally { Pop-Location } }
  "test" { Do-Test }
  "image" { Do-Image }
  "flash" { Do-Flash }
  "all" { Do-Setup; Do-Build; Do-Image }
  default { Get-Help $PSCommandPath -Detailed | Out-String | Write-Host }
}

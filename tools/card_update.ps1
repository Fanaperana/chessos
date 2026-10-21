# Update ChessOS on an already-flashed card (run as Administrator; setup.ps1 update starts it).
# 1) read the ArkOS root partition  2) refresh /opt/chessos in a copy (WSL)
# 3) write back only the changed 4 MiB blocks, each verified.
param(
  [Parameter(Mandatory = $true)][int]$Disk,
  [Parameter(Mandatory = $true)][long]$ExpectedSize,
  [Parameter(Mandatory = $true)][string]$WorkDir,
  [Parameter(Mandatory = $true)][string]$Log,
  [string]$Python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
)
Start-Transcript -Path $Log -Force | Out-Null
$ErrorActionPreference = "Stop"
function Run-Py {
  # plain call operator: the cmd /c quoting form fails in some elevated sessions
  $pylog = Join-Path $WorkDir "update.python.log"
  & $Python -u (Join-Path $PSScriptRoot "sdcard.py") @args *> $pylog
  $code = $LASTEXITCODE
  Get-Content $pylog | Select-Object -Last 3 | ForEach-Object { Write-Host "  $_" }
  if ($code -ne 0) { throw "sdcard.py $($args[0]) failed" }
}
try {
  $d = Get-Disk -Number $Disk
  if ($d.IsBoot -or $d.IsSystem -or $d.BusType -notin @("USB", "SD", "MMC") -or $d.Size -ne $ExpectedSize) {
    throw "Disk $Disk is not the confirmed SD card. Nothing changed."
  }
  $old = Join-Path $WorkDir "card_root.ext4"
  $new = Join-Path $WorkDir "card_root_new.ext4"
  Write-Host "1/3 reading the ArkOS system partition (8.6 GB)"
  $ErrorActionPreference = "Continue"
  Run-Py read-part $Disk $ExpectedSize 2 $old
  Write-Host "2/3 refreshing ChessOS in a copy"
  Copy-Item $old $new -Force
  $wNew = (& wsl.exe -e wslpath -a ($new -replace '\\', '/')).Trim()
  $wRepo = (& wsl.exe -e wslpath -a ((Resolve-Path "$PSScriptRoot\..").Path -replace '\\', '/')).Trim()
  & wsl.exe -e bash "$wRepo/tools/image/install_app.sh" $wNew $wRepo
  if ($LASTEXITCODE -ne 0) { throw "install_app.sh failed" }
  Write-Host "3/3 writing changed blocks"
  Run-Py write-diff $Disk $ExpectedSize 2 $old $new
  Remove-Item $old, $new -Force
  Write-Host "ALL DONE"
} catch {
  Write-Host "ERROR: $_"
} finally {
  Stop-Transcript | Out-Null
}

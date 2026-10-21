# Write an image to an SD card. Must run as Administrator (setup.ps1 flash starts it).
# Refuses system/boot disks, non-USB/SD disks, and any disk whose size changed
# since you confirmed it.
param(
  [Parameter(Mandatory = $true)][int]$Disk,
  [Parameter(Mandatory = $true)][long]$ExpectedSize,
  [Parameter(Mandatory = $true)][string]$Image,
  [Parameter(Mandatory = $true)][string]$Log,
  [string]$Python = "$PSScriptRoot\..\.venv\Scripts\python.exe"
)
Start-Transcript -Path $Log -Force | Out-Null
$ErrorActionPreference = "Stop"
try {
  $d = Get-Disk -Number $Disk
  if ($d.IsBoot -or $d.IsSystem) { throw "Disk $Disk is a system disk. Nothing written." }
  if ($d.BusType -notin @("USB", "SD", "MMC")) { throw "Disk $Disk is $($d.BusType), not a USB/SD card. Nothing written." }
  if ($d.Size -ne $ExpectedSize) { throw "Disk $Disk size changed ($($d.Size)). Nothing written." }
  Write-Host "Target: Disk $Disk, $($d.FriendlyName), $([math]::Round($d.Size/1GB,1)) GB"
  if ($d.PartitionStyle -ne "RAW") {
    Write-Host "Erasing old partitions..."
    Clear-Disk -Number $Disk -RemoveData -RemoveOEM -Confirm:$false
  }
  $ErrorActionPreference = "Continue"
  $pylog = [IO.Path]::ChangeExtension($Log, ".python.log")
  & cmd.exe /c "`"$Python`" -u `"$PSScriptRoot\sdcard.py`" write-image $Disk $ExpectedSize `"$Image`" > `"$pylog`" 2>&1"
  $code = $LASTEXITCODE
  Get-Content $pylog | ForEach-Object { Write-Host $_ }
  if ($code -ne 0) { throw "write failed (exit $code)" }
  Write-Host "ALL DONE. Close this window and eject the card. If Windows offers to format it: Cancel."
} catch {
  Write-Host "ERROR: $_"
} finally {
  Stop-Transcript | Out-Null
}

# Admin: run chkdsk /f on the card's BOOT (FAT) and EASYROMS (exFAT) drives.
param([Parameter(Mandatory = $true)][string]$Log)
Start-Transcript -Path $Log -Force | Out-Null
foreach ($label in "BOOT", "EASYROMS") {
  $v = Get-Volume | Where-Object FileSystemLabel -eq $label | Select-Object -First 1
  if (-not $v) { Write-Host "$label not found"; continue }
  $dl = $v.DriveLetter
  Write-Host "$label ($dl`:) before: $($v.OperationalStatus)"
  & chkdsk.exe "$dl`:" /f /x | Select-Object -Last 6 | ForEach-Object { Write-Host "  $_" }
  Write-Host "$label after: $((Get-Volume -DriveLetter $dl).OperationalStatus)"
}
Stop-Transcript | Out-Null

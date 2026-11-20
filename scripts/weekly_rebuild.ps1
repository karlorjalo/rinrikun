# Build the index again: the new anime and the new links from AniList, and the changes of the
# Jellyfin library. Your tiers and your other data stay. The scheduled task from
# install_weekly_task.ps1 runs this script one time each week. The log is scratch\rebuild.log.
#
#   powershell -ExecutionPolicy Bypass -File scripts\weekly_rebuild.ps1
#
# The build is the Rust program (server\target\release\rinrikun.exe build): see server\README.md.
# The server needs no restart: it loads the data again when the database changes.

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force scratch | Out-Null
$log = Join-Path $root "scratch\rebuild.log"
# Keep the log small: start a new log when the log is larger than 5 MB
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Move-Item $log "$log.old" -Force }

function Write-Log($text) {
    "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text | Out-File -FilePath $log -Append -Encoding utf8
}

$program = Join-Path $root "server\target\release\rinrikun.exe"
if (-not (Test-Path $program)) {
    Write-Log "the Rust program is not at $program. The server continues with the old index."
    exit 1
}

Write-Log "rebuild started"
# One copy of the database from before the build
if (Test-Path anime_vec.db) { Copy-Item anime_vec.db scratch\anime_vec.db.bak-weekly -Force }

# cmd writes the output of the build to the log
cmd /c "`"$program`" build --root `"$root`" >> `"$log`" 2>&1"
if ($LASTEXITCODE -ne 0) {
    Write-Log "the build failed with code $LASTEXITCODE. The server continues with the old index."
    exit 1
}
Write-Log "rebuild finished"

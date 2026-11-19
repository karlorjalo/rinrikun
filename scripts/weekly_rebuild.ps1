# Build the index again, then start the server again.
# The scheduled task from install_weekly_task.ps1 runs this script one time each week.
#
# The build gets the new anime and the new links from AniList, and the changes of the Jellyfin
# library. Your tiers and your other data stay. The log is scratch\rebuild.log.
#
#   powershell -ExecutionPolicy Bypass -File scripts\weekly_rebuild.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\weekly_rebuild.ps1 -Builder rust
#
# -Builder python (the default) runs build.py. -Builder rust runs the Rust build
# (server\target\release\rinrikun.exe build): the same steps and the same database, see
# server\README.md. The PC has no Rust: build the program on a different computer and copy it there.
#
# -NoRestart does not start the servers again. Use it for a test in a second copy of the project:
# restart_servers.ps1 uses the ports of the live server.
param(
    [ValidateSet("python", "rust")]
    [string]$Builder = "python",
    [switch]$NoRestart
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
New-Item -ItemType Directory -Force scratch | Out-Null
$log = Join-Path $root "scratch\rebuild.log"
# Keep the log small: start a new log when the log is larger than 5 MB
if ((Test-Path $log) -and ((Get-Item $log).Length -gt 5MB)) { Move-Item $log "$log.old" -Force }

function Write-Log($text) {
    "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $text | Out-File -FilePath $log -Append -Encoding utf8
}

Write-Log "rebuild started ($Builder)"
# One copy of the database from before the build
if (Test-Path anime_vec.db) { Copy-Item anime_vec.db scratch\anime_vec.db.bak-weekly -Force }

if ($Builder -eq "rust") {
    $program = Join-Path $root "server\target\release\rinrikun.exe"
    if (-not (Test-Path $program)) {
        Write-Log "the Rust program is not at $program. The server continues with the old index."
        exit 1
    }
    # cmd writes the output of the build to the log
    cmd /c "`"$program`" build --root `"$root`" >> `"$log`" 2>&1"
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { $python = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\python.exe" }
    cmd /c "`"$python`" -u build.py >> `"$log`" 2>&1"
}
if ($LASTEXITCODE -ne 0) {
    Write-Log "the build failed with code $LASTEXITCODE. The server continues with the old index."
    exit 1
}
Write-Log "build done"

if ($NoRestart) {
    Write-Log "rebuild finished (the servers were not started again)"
    exit 0
}
# The Python server reads the index only when it starts
& (Join-Path $PSScriptRoot "restart_servers.ps1") | Out-File -FilePath $log -Append -Encoding utf8
Write-Log "rebuild finished"

# Build the page (the folder web\).
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_web.ps1
#
# The build is in web\build. Its Node server renders the pages (node web\build), and it
# reads the build when it starts. Thus start it again after a build:
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1 -WebOnly
param(
    # Do not install the packages again. Use this if web\node_modules is correct already.
    [switch]$NoInstall
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "web")

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    "Node.js is not installed. The build of the page needs it."
    exit 1
}

# PowerShell does not permit npm.ps1 on each computer. npm.cmd does the same work.
if (-not $NoInstall) {
    cmd /c "npm.cmd ci"
    if ($LASTEXITCODE -ne 0) {
        "The installation of the packages failed with code $LASTEXITCODE."
        exit 1
    }
}
cmd /c "npm.cmd run build"
if ($LASTEXITCODE -ne 0) {
    "The build failed with code $LASTEXITCODE. The page server continues with the old build, if there is one."
    exit 1
}
"The page is in web\build. Start its server again: scripts\restart_servers.ps1 -WebOnly"

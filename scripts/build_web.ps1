# Build the new page (the folder web\) so that the server can give it at /next.
#
#   powershell -ExecutionPolicy Bypass -File scripts\build_web.ps1
#
# The build is in web\build. The server gives the new page only if that folder is there, and it
# looks for it when it starts. Thus start the server again after the first build
# (scripts\restart_servers.ps1). A later build needs no restart.
param(
    # Do not install the packages again. Use this if web\node_modules is correct already.
    [switch]$NoInstall
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "web")

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    "Node.js is not installed. The build of the new page needs it."
    exit 1
}

# The server gives the page below /next, thus the addresses in the page must start with /next
$env:BASE_PATH = "/next"

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
    "The build failed with code $LASTEXITCODE. The server continues with the old build, if there is one."
    exit 1
}
"The new page is in web\build. The server gives it at /next."

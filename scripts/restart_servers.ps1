# Stop the rinrikun servers and start them again.
# The servers have no window, and they continue to run when this script ends.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1 -WebOnly
#
# There are two servers:
#   - The Python server (serve.py): the API, the old page at /, and the address of the new page.
#     One process listens on all addresses. Each address is "address:port". The first default
#     address accepts connections only from this computer. The second default address accepts
#     connections from other computers.
#   - The Node server of the new page: the server of the SvelteKit build (node web\build). It
#     renders the pages of /next, and it listens only on this computer, on the port -WebPort. The
#     Python server passes the requests for /next on to it. It starts only if the build of the new
#     page is there (scripts\build_web.ps1).
#
# -WebOnly starts only the Node server again, for example after a new build of the page.
#
# Do not start one Python process for each address. A server keeps your tiers and your answers in
# memory, and it reads the database only when it starts. Thus two processes do not agree after
# you change a tier through one of them.
param(
    [string[]]$Addresses = @("127.0.0.1:8765", "0.0.0.0:8771"),
    [string]$Log = "serve.log",
    [int]$WebPort = 8780,
    [string]$WebLog = "web.log",
    [switch]$WebOnly
)

# "powershell -File" gives a list with commas as one text: -Addresses 127.0.0.1:8765,0.0.0.0:8771
$Addresses = @($Addresses | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\python.exe" }
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
$first = $Addresses[0]
$split = $first.LastIndexOf(":")
$firstHost = $first.Substring(0, $split)
$firstPort = $first.Substring($split + 1)

# Stop the processes that listen on the ports
$ports = @($WebPort)
if (-not $WebOnly) { $ports += $Addresses | ForEach-Object { [int]($_ -split ":")[-1] } }
$old = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $ports } | Select-Object -ExpandProperty OwningProcess -Unique
if ($old) { Stop-Process -Id $old -Force -Confirm:$false }
Start-Sleep -Seconds 2

# WMI starts the processes. A process is not a child of this script, thus it continues to run
# when the script ends. "set" gives the process its environment.
function Start-Detached($command) {
    (Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $root }).ReturnValue
}

if (-not $WebOnly) {
    $options = "--no-browser --host {0} --port {1}" -f $firstHost, $firstPort
    foreach ($address in ($Addresses | Select-Object -Skip 1)) { $options += " --also $address" }
    $command = 'cmd /c "set RINRIKUN_WEB=http://127.0.0.1:{0}&& "{1}" serve.py {2} >> "{3}" 2>&1"' -f $WebPort, $python, $options, $Log
    "server started on {0} (return value {1})" -f ($Addresses -join " and "), (Start-Detached $command)
}

if (-not (Test-Path (Join-Path $root "web\build\index.js"))) {
    "the new page is not built: no server for /next (see scripts\build_web.ps1)"
} elseif (-not $node) {
    "Node.js is not installed: no server for /next"
} else {
    # The API of the Python server, at its first address. An address for all networks is also on this computer.
    $apiHost = if ($firstHost -eq "0.0.0.0") { "127.0.0.1" } else { $firstHost }
    $command = 'cmd /c "set HOST=127.0.0.1&& set PORT={0}&& set API_TARGET=http://{1}:{2}&& "{3}" web\build >> "{4}" 2>&1"' -f $WebPort, $apiHost, $firstPort, $node, $WebLog
    "page server started on 127.0.0.1:{0} (return value {1})" -f $WebPort, (Start-Detached $command)
}

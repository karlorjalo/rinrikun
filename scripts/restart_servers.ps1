# Stop the rinrikun servers and start them again.
# The servers have no window, and they continue to run when this script ends.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1 -WebOnly
#
# There are two servers:
#   - The Rust server (server\target\release\rinrikun.exe serve): the API, and the address of the
#     page. One process listens on all addresses. Each address is "address:port". The first
#     default address accepts connections only from this computer. The second default address
#     accepts connections from other computers.
#   - The page server: the server of the SvelteKit build (node web\build). It renders the pages,
#     and it listens only on this computer, on the port -WebPort. The Rust server passes each
#     request that is not for /api on to it. It starts only if the build of the page is there
#     (scripts\build_web.ps1).
#
# -WebOnly starts only the page server again, for example after a new build of the page.
#
# The PC has no Rust: build the program on a different computer (cargo build --release in server\)
# and copy it to server\target\release\rinrikun.exe.
#
# Start one Rust process for all addresses: the server keeps your data in memory, and two
# processes would not agree after a change through one of them.
param(
    [string[]]$Addresses = @("127.0.0.1:8765", "0.0.0.0:8771"),
    [string]$Database = "anime_vec.db",
    [string]$Log = "serve.log",
    [int]$WebPort = 8780,
    [string]$WebLog = "web.log",
    [switch]$WebOnly
)

# "powershell -File" gives a list with commas as one text: -Addresses 127.0.0.1:8765,0.0.0.0:8771
$Addresses = @($Addresses | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$root = Split-Path -Parent $PSScriptRoot
$program = Join-Path $root "server\target\release\rinrikun.exe"
$node = (Get-Command node -ErrorAction SilentlyContinue).Source
$first = $Addresses[0]
$split = $first.LastIndexOf(":")
$firstHost = $first.Substring(0, $split)
$firstPort = $first.Substring($split + 1)

if (-not $WebOnly -and -not (Test-Path $program)) {
    "the Rust program is not at ${program}: nothing was stopped"
    exit 1
}

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
    $options = ($Addresses | ForEach-Object { "--listen $_" }) -join " "
    $command = 'cmd /c ""{0}" serve "{1}" {2} --root "{3}" --web http://127.0.0.1:{4} >> "{5}" 2>&1"' -f $program, $Database, $options, $root, $WebPort, $Log
    "server started on {0} (return value {1})" -f ($Addresses -join " and "), (Start-Detached $command)
}

if (-not (Test-Path (Join-Path $root "web\build\index.js"))) {
    "the page is not built: no page server (see scripts\build_web.ps1)"
} elseif (-not $node) {
    "Node.js is not installed: no page server"
} else {
    # The API at the first address of the Rust server. An address for all networks is also on this computer.
    $apiHost = if ($firstHost -eq "0.0.0.0") { "127.0.0.1" } else { $firstHost }
    $command = 'cmd /c "set HOST=127.0.0.1&& set PORT={0}&& set API_TARGET=http://{1}:{2}&& "{3}" web\build >> "{4}" 2>&1"' -f $WebPort, $apiHost, $firstPort, $node, $WebLog
    "page server started on 127.0.0.1:{0} (return value {1})" -f $WebPort, (Start-Detached $command)
}

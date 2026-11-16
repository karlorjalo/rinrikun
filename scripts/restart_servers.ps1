# Stop the rinrikun servers and start them again.
# The servers have no window, and they continue to run when this script ends.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1
#
# Each server is "address:port:log file". The first default server accepts connections only from
# this computer. The second default server accepts connections from other computers.
param(
    [string[]]$Servers = @("127.0.0.1:8765:serve.log", "0.0.0.0:8771:scratch\serve-8771.log")
)

$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\python.exe" }
New-Item -ItemType Directory -Force (Join-Path $root "scratch") | Out-Null

# Stop the processes that listen on the ports of the servers
$ports = $Servers | ForEach-Object { [int]($_ -split ":")[1] }
$old = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $ports } | Select-Object -ExpandProperty OwningProcess -Unique
if ($old) { Stop-Process -Id $old -Force -Confirm:$false }
Start-Sleep -Seconds 2

foreach ($server in $Servers) {
    $address, $port, $log = $server -split ":", 3
    $command = 'cmd /c ""{0}" -m uvicorn serve:app --host {1} --port {2} >> "{3}" 2>&1"' -f $python, $address, $port, $log
    # WMI starts the process. The process is not a child of this script, thus it continues to run
    # when the script ends.
    $result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $root }
    "{0}:{1} started (return value {2})" -f $address, $port, $result.ReturnValue
}

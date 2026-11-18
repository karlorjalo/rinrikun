# Stop the rinrikun server and start it again.
# The server has no window, and it continues to run when this script ends.
#
#   powershell -ExecutionPolicy Bypass -File scripts\restart_servers.ps1
#
# One server process listens on all addresses. Each address is "address:port". The first default
# address accepts connections only from this computer. The second default address accepts
# connections from other computers.
#
# Do not start one process for each address. A server keeps your tiers and your answers in
# memory, and it reads the database only when it starts. Thus two processes do not agree after
# you change a tier through one of them.
param(
    [string[]]$Addresses = @("127.0.0.1:8765", "0.0.0.0:8771"),
    [string]$Log = "serve.log"
)

# "powershell -File" gives a list with commas as one text: -Addresses 127.0.0.1:8765,0.0.0.0:8771
$Addresses = @($Addresses | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\python.exe" }

# Stop the processes that listen on the ports of the addresses
$ports = $Addresses | ForEach-Object { [int]($_ -split ":")[-1] }
$old = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -in $ports } | Select-Object -ExpandProperty OwningProcess -Unique
if ($old) { Stop-Process -Id $old -Force -Confirm:$false }
Start-Sleep -Seconds 2

$first = $Addresses[0]
$split = $first.LastIndexOf(":")
$options = "--no-browser --host {0} --port {1}" -f $first.Substring(0, $split), $first.Substring($split + 1)
foreach ($address in ($Addresses | Select-Object -Skip 1)) { $options += " --also $address" }
$command = 'cmd /c ""{0}" serve.py {1} >> "{2}" 2>&1"' -f $python, $options, $Log
# WMI starts the process. The process is not a child of this script, thus it continues to run
# when the script ends.
$result = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = $command; CurrentDirectory = $root }
"server started on {0} (return value {1})" -f ($Addresses -join " and "), $result.ReturnValue

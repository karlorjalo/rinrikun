# The times of the API, of the pages and of the data of the tabs, and the times after a change.
# Run it on the PC against the dev copy only:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\perf\api_times.ps1
#
# The script requests lists of recommendations without a seed and changes a tier (to the tier
# that the show has already). On the live server, each such list would go into the log of the
# user. Thus the script stops before its first request if one of these is not true:
#   - The server at -Base runs from the folder rinrikun-dev.
#   - The page server at -Web, and the page server that the server at -Base passes its pages on
#     to (its option --web), use the server at -Base as their API (API_TARGET in their start
#     command). The script requests /recommendations on both.
# -CheckOnly makes only these checks and sends no request.
#
# Each line: the time of the first request, the times of the next requests, the time to the
# first byte of the last request, the size with gzip and the size without gzip.
param(
    [string]$Base = "http://127.0.0.1:8773",
    [string]$Web = "http://127.0.0.1:8781",
    [switch]$CheckOnly
)
$ProgressPreference = "SilentlyContinue"

function Get-Listener([int]$Port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { throw "nothing listens on port $Port" }
    Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
}

# The page server at an address must use the API at -Base. restart_servers.ps1 starts it with
# "cmd /c set API_TARGET=...": that command is the parent process of the page server.
function Assert-DevPage([string]$Address, [int]$ApiPort) {
    $process = Get-Listener ([uri]$Address).Port
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
    $wanted = "API_TARGET=http://(127\.0\.0\.1|localhost):$ApiPort(?!\d)"
    if (-not $parent -or $parent.CommandLine -notmatch $wanted) {
        throw "the page server at $Address does not use the API on port ${ApiPort}: $($parent.CommandLine)"
    }
}

$port = ([uri]$Base).Port
$command = (Get-Listener $port).CommandLine
if ($command -notmatch "rinrikun-dev") { throw "the server on port $port is not the dev copy: $command" }
Assert-DevPage $Web $port
if ($command -match "--web\s+(\S+)") { Assert-DevPage $Matches[1] $port } else { throw "the server on port $port has no --web option: $command" }
if ($CheckOnly) { "the checks pass: $Base and $Web are the dev copy"; exit 0 }

$rated = Invoke-RestMethod "$Base/api/ratings"
$id = [uri]::EscapeDataString($rated[0].id)
"rated shows: $($rated.Count), the show of the tests: $id"

function Measure-Address([string]$Url, [int]$Runs = 3) {
    $times = @()
    for ($n = 0; $n -lt $Runs; $n++) {
        $out = curl.exe -s -o NUL -w "%{time_starttransfer} %{time_total} %{size_download}" -H "Accept-Encoding: gzip" $Url
        $times += , ($out -split " ")
    }
    $raw = curl.exe -s -o NUL -w "%{size_download}" $Url
    $first = [math]::Round([double]$times[0][1] * 1000)
    $next = ($times | Select-Object -Skip 1 | ForEach-Object { [math]::Round([double]$_[1] * 1000) }) -join "/"
    $firstByte = [math]::Round([double]$times[-1][0] * 1000)
    "{0,-72} first {1,5} ms, then {2,-11} first byte {3,5} | gzip {4,9} B, raw {5,9} B" -f $Url.Replace($Base, "").Replace($Web, "WEB"), $first, $next, $firstByte, $times[-1][2], $raw
}

"== API"
$list = "/api/recommend?k=40&mode=hybrid&kinds=usual&links=true&new_only=true"
foreach ($path in @(
        "/api/profile", "/api/rec-log", "/api/interest/results",
        "/api/discover?count=12", "/api/interest",
        "/api/ratings", "/api/watched", "/api/dismissed",
        "/api/review-queue?unrated_only=true", "/api/review-queue?unrated_only=false",
        "/api/similar?id=$id&k=24", "/api/similar?id=$id&k=48", "/api/show/$id",
        $list,
        "/api/recommend?k=40&mode=diverse&kinds=usual&links=true&new_only=true",
        "/api/recommend?k=40&mode=hybrid&kinds=all&links=false&new_only=false",
        "$list&seed=$id",
        "/api/recommend/steps?k=40&new_only=true&kinds=usual&links=true",
        "/api/vector-map", "/api/vector-map/match", "/api/shows", "/api/weights")) {
    Measure-Address "$Base$path"
}

"== Pages (through the Rust server, then directly on the page server)"
$pages = @("/", "/discover", "/ratings", "/review", "/similar", "/similar?id=$id", "/recommendations", "/settings")
foreach ($path in $pages) { Measure-Address "$Base$path" }
foreach ($path in $pages) { Measure-Address "$Web$path" }

"== Data of the tabs (the request of a change of the tab)"
foreach ($path in @("/__data.json", "/discover/__data.json", "/ratings/__data.json", "/review/__data.json", "/similar/__data.json", "/similar/__data.json?id=$id", "/recommendations/__data.json")) {
    Measure-Address "$Base$path"
}

"== After a change (a POST that gives a show the tier that it has already)"
$show = $rated | Where-Object { $_.tier -eq "B" } | Select-Object -First 1
if (-not $show) { $show = $rated[0] }
$showId = [uri]::EscapeDataString($show.id)
$body = Join-Path $env:TEMP "rinrikun-perf-tier.json"
[IO.File]::WriteAllText($body, (@{ id = $show.id; tier = $show.tier } | ConvertTo-Json -Compress))
function Measure-Once([string]$Label, [string[]]$Arguments) {
    $out = curl.exe -s -o NUL -w "%{time_total}" @Arguments
    "{0,-48} {1,6} ms" -f $Label, [math]::Round([double]$out * 1000)
}
function Send-Tier { Measure-Once "POST /api/weights" @("-X", "POST", "-H", "Content-Type: application/json", "--data-binary", "@$body", "$Base/api/weights") }
Send-Tier
Measure-Once "GET /api/show at once" @("$Base/api/show/$showId")
Send-Tier
Start-Sleep -Seconds 1
Measure-Once "GET /api/show 1 s after the POST" @("$Base/api/show/$showId")
Send-Tier
Measure-Once "GET /ratings/__data.json at once" @("$Base/ratings/__data.json")
Send-Tier
Measure-Once "GET /review/__data.json at once" @("$Base/review/__data.json")
Send-Tier
Start-Sleep -Seconds 1
Measure-Once "GET /api/recommend 1 s after the POST" @("$Base$list")
Remove-Item $body -ErrorAction SilentlyContinue

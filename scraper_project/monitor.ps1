
# Freedom Wall Scraper -- Autonomous Monitor & Self-Healer
# Runs in its own PowerShell window until all 10 targets hit 4000 posts.

$base    = "C:\Users\Alex Evan\Documents\Research\scraper_project"
$python  = "C:\Python314\python.exe"
$alog    = "$base\logs\AGENT_ACTIONS.log"
$outLog  = "$base\logs\agent_stdout.log"
$errLog  = "$base\logs\agent_stderr.log"
$data    = "$base\data"

$targets       = @("FW-01","FW-02","FW-03","FW-04","FW-05","FW-06","FW-07","FW-08","FW-09","SLU")
$targetPosts   = 4000
$skipThreshold = 100
$freezeSecs    = 660
$checkInterval = 30

function ts   { Get-Date -Format "yyyy-MM-dd HH:mm:ss" }
function log  {
    param($msg)
    $line = "[$(ts)] $msg"
    Add-Content -Path $alog -Value $line
    Write-Host $line
}

function Get-PostCount {
    param($code)
    $f = "$data\$code.jsonl"
    if (Test-Path $f) {
        $content = Get-Content $f -Raw
        if ($content) { ($content -split "`n" | Where-Object { $_ -ne "" }).Count }
        else { 0 }
    } else { 0 }
}

function Is-ScraperAlive {
    $null -ne (Get-Process python -ErrorAction SilentlyContinue)
}

function Start-Scraper {
    param([string[]]$targs)
    if ($targs -and $targs.Count -gt 0) {
        $targStr = $targs -join " "
        $argStr = "main.py --cookies cookies.json --target-posts $targetPosts --targets $targStr"
    } else {
        $argStr = "main.py --cookies cookies.json --target-posts $targetPosts"
    }
    log "LAUNCH -- $python $argStr"
    $p = Start-Process -FilePath $python -ArgumentList $argStr `
             -WorkingDirectory $base `
             -RedirectStandardOutput $outLog `
             -RedirectStandardError  $errLog `
             -WindowStyle Hidden -PassThru
    log "LAUNCH -- PID=$($p.Id)"
    return $p
}

function Kill-Scraper {
    log "KILL -- Terminating all python.exe processes"
    Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 10
}

function Do-Maintenance {
    $disk = Get-PSDrive -Name C -ErrorAction SilentlyContinue
    if ($disk -and $disk.Free -lt 5GB) {
        log "DISK_WARN -- Less than 5 GB free ($([math]::Round($disk.Free/1GB,2)) GB)"
    }
    $ssDir = "$base\debug_screenshots"
    if (Test-Path $ssDir) {
        Get-ChildItem $ssDir -File |
            Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-1) } |
            Remove-Item -Force
    }
    if (-not (Test-Path "$base\cookies.json")) {
        log "COOKIE_MISSING -- cookies.json not found!"
    }
}

log "MONITOR_START -- Autonomous monitor v2 (PowerShell). Targets: $($targets -join ', '). Goal: $targetPosts posts each."

$doneCodes = @()
foreach ($c in $targets) {
    $cnt = Get-PostCount $c
    if ($cnt -ge $targetPosts) {
        $doneCodes += $c
        log "ALREADY_DONE -- $c has $cnt posts"
    }
}
$remaining = $targets | Where-Object { $doneCodes -notcontains $_ }

if ($remaining.Count -eq 0) {
    log "ALL_DONE -- All targets already completed."
    exit 0
}

if (-not (Is-ScraperAlive)) {
    Start-Scraper -targs $remaining
} else {
    log "SCRAPER_FOUND -- Existing python process detected. Monitoring it."
}

$lastCounts     = @{}
$lastGrowthTime = @{}

foreach ($c in $remaining) {
    $lastCounts[$c]     = Get-PostCount $c
    $lastGrowthTime[$c] = Get-Date
}

$maintenanceTick = 0

while ($true) {
    Start-Sleep -Seconds $checkInterval
    $maintenanceTick++
    if ($maintenanceTick % 60 -eq 0) { Do-Maintenance }

    $remaining = $targets | Where-Object {
        (Get-PostCount $_) -lt $targetPosts -and
        -not (Test-Path "$data\$_.skipped")
    }

    if ($remaining.Count -eq 0) {
        log "ALL_DONE -- All targets reached $targetPosts posts or were skipped."
        exit 0
    }

    $alive = Is-ScraperAlive

    foreach ($code in $remaining) {
        $cnt   = Get-PostCount $code
        $prev  = if ($lastCounts.ContainsKey($code)) { $lastCounts[$code] } else { 0 }
        $delta = $cnt - $prev

        if ($delta -gt 0) {
            log "MONITOR -- ${code}: $cnt/$targetPosts posts (+$delta). Python=$alive"
            $lastCounts[$code]     = $cnt
            $lastGrowthTime[$code] = Get-Date
        } else {
            $stallSecs = [int]((Get-Date) - $lastGrowthTime[$code]).TotalSeconds
            log "MONITOR -- ${code}: $cnt/$targetPosts posts (no growth ${stallSecs}s). Python=$alive"

            if (-not $alive -and $cnt -lt $skipThreshold -and $stallSecs -gt 300) {
                log "SKIP -- ${code}: only $cnt posts after ${stallSecs}s stall. Skipping."
                "" | Out-File "$data\$code.skipped"
            }
        }
    }

    if (-not $alive) {
        $activeCode = $remaining[0]
        $cnt = Get-PostCount $activeCode
        log "RESTART -- Python dead. Active=${activeCode} at $cnt posts. Restarting."
        Start-Scraper -targs $remaining
        foreach ($c in $remaining) { $lastGrowthTime[$c] = Get-Date }
    } else {
        $activeCode = $remaining[0]
        if ($lastGrowthTime.ContainsKey($activeCode)) {
            $stallSecs = [int]((Get-Date) - $lastGrowthTime[$activeCode]).TotalSeconds
            if ($stallSecs -gt $freezeSecs) {
                log "FREEZE -- ${activeCode} frozen ${stallSecs}s with python alive. Kill+restart."
                Kill-Scraper
                Start-Scraper -targs $remaining
                foreach ($c in $remaining) { $lastGrowthTime[$c] = Get-Date }
            }
        }
    }
}


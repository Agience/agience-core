param(
    [Parameter(Mandatory = $true)]
    [string]$Token,

    [string]$AuthorityUrl = "http://localhost:8081",

    [string]$DesktopHostUrl = "http://127.0.0.1:8082",

    [int]$TimeoutSeconds = 20,

    [int]$PollIntervalSeconds = 2
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Json {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [hashtable]$Headers = @{}
    )

    Invoke-RestMethod -Uri $Uri -Headers $Headers -Method Get
}

function Wait-ForRelayConnection {
    param(
        [Parameter(Mandatory = $true)]
        [string]$DesktopStatusUri,

        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,

        [Parameter(Mandatory = $true)]
        [int]$PollIntervalSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastStatus = $null

    while ((Get-Date) -lt $deadline) {
        try {
            $lastStatus = Invoke-Json -Uri $DesktopStatusUri
            if ($lastStatus.connected -eq $true) {
                return $lastStatus
            }
        }
        catch {
            $lastStatus = $null
        }

        Start-Sleep -Seconds $PollIntervalSeconds
    }

    if ($null -ne $lastStatus) {
        return $lastStatus
    }

    throw "Timed out waiting for desktop relay status endpoint at $DesktopStatusUri"
}

$authoritySessionsUri = "$($AuthorityUrl.TrimEnd('/'))/relay/sessions/me"
$desktopStatusUri = "$($DesktopHostUrl.TrimEnd('/'))/relay/status"
$headers = @{ Authorization = "Bearer $Token" }

Write-Step "Checking desktop host relay status"
$desktopStatus = Wait-ForRelayConnection -DesktopStatusUri $desktopStatusUri -TimeoutSeconds $TimeoutSeconds -PollIntervalSeconds $PollIntervalSeconds

Write-Host "configured: $($desktopStatus.configured)"
Write-Host "connected : $($desktopStatus.connected)"
Write-Host "session_id: $($desktopStatus.session_id)"
if ($desktopStatus.last_error) {
    Write-Host "last_error: $($desktopStatus.last_error)" -ForegroundColor Yellow
}

if ($desktopStatus.configured -ne $true) {
    throw "Desktop host is not configured. Check authority_url and access_token in the desktop config."
}

if ($desktopStatus.connected -ne $true) {
    throw "Desktop host is configured but not connected to the authority."
}

Write-Step "Checking authority-side relay session"
$sessionResponse = Invoke-Json -Uri $authoritySessionsUri -Headers $headers

if (-not $sessionResponse.sessions -or $sessionResponse.sessions.Count -lt 1) {
    throw "Authority did not return any active relay sessions for the supplied token."
}

$session = $sessionResponse.sessions[0]
$manifest = $session.capabilities_manifest
$desktopServerId = if ($manifest.server_id) { [string]$manifest.server_id } else { "desktop-host" }
$builtInTools = @()
if ($manifest.tools) {
    $builtInTools = @($manifest.tools | ForEach-Object { [string]$_ })
}
$localServers = @()
if ($manifest.local_servers) {
    $localServers = @($manifest.local_servers | ForEach-Object {
        if ($_.server_id) { [string]$_.server_id } else { "" }
    })
}

Write-Host "display_name: $($session.display_name)"
Write-Host "device_id   : $($session.device_id)"
Write-Host "server_id   : $desktopServerId"
Write-Host "tools       : $($builtInTools -join ', ')"
Write-Host "local_mcp   : $($localServers -join ', ')"

$requiredTools = @(
    "host_status",
    "fs_list_dir",
    "fs_read_text",
    "mcp_servers_list_local",
    "mcp_servers_start_local",
    "mcp_servers_stop_local"
)

$missingTools = @($requiredTools | Where-Object { $_ -notin $builtInTools })
if ($missingTools.Count -gt 0) {
    throw "Authority session is missing required desktop-host tools: $($missingTools -join ', ')"
}

$doublePrefixed = @($localServers | Where-Object { $_ -like 'local-mcp:local-mcp:*' })
if ($doublePrefixed.Count -gt 0) {
    throw "Detected invalid double-prefixed local MCP server ids: $($doublePrefixed -join ', ')"
}

Write-Step "Smoke test passed"
Write-Host "Desktop host and authority relay session are both healthy." -ForegroundColor Green
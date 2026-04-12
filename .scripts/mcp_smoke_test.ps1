param(
  [string]$BaseUrl = "http://localhost:8081",
  [string]$Token = $env:AGIENCE_MCP_TOKEN,
  [switch]$ExchangeJwt,
  [int]$ExchangeHours = 8
)

$ErrorActionPreference = "Stop"

function Write-Section([string]$Title) {
  Write-Host "" 
  Write-Host "=== $Title ==="
}

if (-not $BaseUrl) {
  throw "BaseUrl is required"
}

$BaseUrl = $BaseUrl.TrimEnd("/")

Write-Section "Discovery"
$wellKnown = Invoke-RestMethod -Method GET -Uri "$BaseUrl/.well-known/mcp.json" -Headers @{ "Cache-Control" = "no-store" }
$wellKnown | ConvertTo-Json -Depth 10

if (-not $Token) {
  Write-Host "" 
  Write-Host "No token provided. Set AGIENCE_MCP_TOKEN to an API key (agc_...) or JWT and re-run to verify auth."
  exit 0
}

$headers = @{ Authorization = "Bearer $Token" }

Write-Section "Auth UserInfo (/auth/userinfo)"
$whoami = Invoke-RestMethod -Method GET -Uri "$BaseUrl/auth/userinfo" -Headers $headers
$whoami | ConvertTo-Json -Depth 10

if ($ExchangeJwt) {
  Write-Section "API key -> JWT exchange (/api-keys/exchange)"
  $payload = @{ expires_hours = $ExchangeHours } | ConvertTo-Json
  $exchange = Invoke-RestMethod -Method POST -Uri "$BaseUrl/api-keys/exchange" -Headers ($headers + @{ "Content-Type" = "application/json" }) -Body $payload

  # Do not print the token; just confirm shape.
  $safe = @{ token_type = $exchange.token_type; expires_hours = $exchange.expires_hours; scopes = $exchange.scopes; resource_filters = $exchange.resource_filters }
  $safe | ConvertTo-Json -Depth 10
  Write-Host "" 
  Write-Host "JWT received (hidden). If your MCP client needs JWT, set Authorization: Bearer <jwt> using exchange.access_token."
}

Write-Section "Next"
Write-Host "If WhoAmI succeeded, your MCP server is running and auth is valid."
Write-Host "MCP transports: $BaseUrl$($wellKnown.endpoints.sse) (SSE) and $BaseUrl$($wellKnown.endpoints.http) (HTTP)."

param(
    [string]$Base = "main",
    [string]$Head
)

$ErrorActionPreference = "Stop"

if (-not $Head) {
    $Head = (git rev-parse --abbrev-ref HEAD).Trim()
}

if ($Head -eq $Base) {
    throw "Current branch is already '$Base'. Run this from your development lane."
}

$messagePath = (python .scripts/prepare_main_promotion.py --base $Base --head $Head).Trim()

Write-Host "Prepared promotion note: $messagePath"
Write-Host ""
Get-Content $messagePath | Write-Host
Write-Host ""

$confirmation = Read-Host "Promote '$Head' into '$Base' now? [y/N]"
if ($confirmation -notin @('y', 'Y', 'yes', 'YES')) {
    Write-Host "Cancelled. Note left at $messagePath"
    exit 0
}

git checkout $Base
git merge --no-ff $Head --file $messagePath

Write-Host "Merged '$Head' into '$Base' using $messagePath"
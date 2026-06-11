<#
.SYNOPSIS
    Roll back a stable tag release (vX.Y.Z) so the version can be re-tagged.

.DESCRIPTION
    Undoes the release artifacts created by tag-stable.ps1 / publish_public.ps1:
      - deletes the local tag vX.Y.Z
      - deletes the tag on the public remote (and origin, if present)
      - deletes the GitHub Release vX.Y.Z on the public repo (via gh)

    Only deletes what actually exists. Asks for confirmation unless -Force.

    Deliberately does NOT:
      - rewrite branch history (the "Bump version to X.Y.Z" commit and the
        release/X.Y -> main forward-port merge are left in place), or
      - delete already-published Docker images.
    Both are reported as manual follow-ups at the end.

.PARAMETER Version
    Full patch version to roll back (X.Y.Z - e.g. 0.3.1).

.PARAMETER Force
    Skip the confirmation prompt.

.EXAMPLE
    .\.scripts\rollback-stable.ps1 -Version 0.3.1
#>
param(
    [Parameter(Mandatory)]
    [Alias("v")]
    [string]$Version,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# Validate format
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host "ERROR: Version must be X.Y.Z (for example: 0.3.1)" -ForegroundColor Red
    exit 1
}

$Tag          = "v$Version"
$MinorVersion = $Version -replace '\.\d+$', ''
$PublicRemote = "public"
$OriginRemote = "origin"

# Resolve the public repo (owner/name) from the public remote URL, for gh.
$PublicUrl = (git remote get-url $PublicRemote 2>$null)
if (-not $PublicUrl) {
    Write-Host "ERROR: Remote '$PublicRemote' not found. Expected remote pointing to the public agience-core repo." -ForegroundColor Red
    exit 1
}
if ($PublicUrl -match '[:/]([^/:]+/[^/]+?)(\.git)?$') {
    $PublicRepo = $Matches[1]
} else {
    Write-Host "ERROR: Could not parse owner/repo from public remote URL '$PublicUrl'." -ForegroundColor Red
    exit 1
}

$HasGh = [bool](Get-Command gh -ErrorAction SilentlyContinue)
if (-not $HasGh) {
    Write-Host "WARNING: 'gh' CLI not found - the GitHub Release will NOT be deleted (tags still will be)." -ForegroundColor DarkYellow
}

# Discover what actually exists so we only delete what's there.
$localTag  = "$(git tag -l $Tag)".Trim()
$publicTag = "$(git ls-remote --tags $PublicRemote $Tag 2>$null)".Trim()
$originTag = "$(git ls-remote --tags $OriginRemote $Tag 2>$null)".Trim()
$release   = ""
if ($HasGh) { $release = (gh release view $Tag --repo $PublicRepo --json tagName 2>$null) }

Write-Host ""
Write-Host "=== Rollback $Tag ===" -ForegroundColor Cyan
Write-Host "  Public repo     : $PublicRepo"
Write-Host "  Local tag       : $([bool]$localTag)"
Write-Host "  Tag on public   : $([bool]$publicTag)"
Write-Host "  Tag on origin   : $([bool]$originTag)"
Write-Host "  GitHub Release  : $([bool]$release)"
Write-Host ""

if (-not ($localTag -or $publicTag -or $originTag -or $release)) {
    Write-Host "  Nothing to roll back for $Tag." -ForegroundColor Yellow
    exit 0
}

# Confirm (destructive). Require typing the version back.
if (-not $Force) {
    $confirm = Read-Host "  Delete the above $Tag artifacts? Type the version ($Version) to confirm"
    if ($confirm -ne $Version) {
        Write-Host "  Aborted - input did not match." -ForegroundColor Yellow
        exit 1
    }
}

# 1. GitHub Release
if ($release) {
    Write-Host "  Deleting GitHub Release $Tag on $PublicRepo..." -ForegroundColor Cyan
    gh release delete $Tag --repo $PublicRepo --yes
    if ($LASTEXITCODE -ne 0) {
        Write-Host "WARNING: Failed to delete GitHub Release (continuing with tag deletion)." -ForegroundColor DarkYellow
    }
}

# 2. Remote tags (deleting the public tag is what un-publishes the release)
if ($publicTag) {
    Write-Host "  Deleting tag on $PublicRemote..." -ForegroundColor Cyan
    git push $PublicRemote ":refs/tags/$Tag"
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: Failed to delete tag on $PublicRemote." -ForegroundColor DarkYellow }
}
if ($originTag) {
    Write-Host "  Deleting tag on $OriginRemote..." -ForegroundColor Cyan
    git push $OriginRemote ":refs/tags/$Tag"
    if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: Failed to delete tag on $OriginRemote." -ForegroundColor DarkYellow }
}

# 3. Local tag
if ($localTag) {
    Write-Host "  Deleting local tag..." -ForegroundColor Cyan
    git tag -d $Tag | Out-Null
}

Write-Host ""
Write-Host "  Rolled back $Tag (tag + GitHub Release)." -ForegroundColor Green
Write-Host ""
Write-Host "  NOT done automatically (external state / history):" -ForegroundColor DarkYellow
Write-Host "    - Docker images for :$Version remain on Docker Hub + GHCR." -ForegroundColor Gray
Write-Host "      :stable and :$MinorVersion are overwritten by the next release;" -ForegroundColor Gray
Write-Host "      delete the immutable :$Version tags by hand if you truly need them gone." -ForegroundColor Gray
Write-Host "    - The 'Bump version to $Version' commit and the release/$MinorVersion -> main" -ForegroundColor Gray
Write-Host "      forward-port merge are left in git history." -ForegroundColor Gray
Write-Host ""
Write-Host "  Re-tag when ready:  Agience: Stable - Tag Release  (version $Version)" -ForegroundColor Gray
Write-Host ""

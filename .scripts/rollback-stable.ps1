<#
.SYNOPSIS
    Roll back a stable tag release (vX.Y.Z) so the version can be re-tagged.

.DESCRIPTION
    Deletes the tag vX.Y.Z everywhere tag-stable.ps1 / publish_public.ps1
    pushed it:
      - the local tag
      - the tag on the public remote  (this un-publishes the release: deleting
        the tag turns its GitHub Release into a draft and CI does not re-run)
      - the tag on origin, if present

    Pure git - no external tools. Only deletes tags that actually exist, and
    asks for confirmation unless -Force.

    Deliberately does NOT:
      - delete the GitHub Release object. Deleting the tag drops it to a draft;
        re-running tag-stable for this version updates it. Remove the draft by
        hand from the repo's Releases page if you want it gone.
      - delete already-published Docker images.
      - rewrite branch history (the "Bump version to X.Y.Z" commit and the
        release/X.Y -> main forward-port merge are left in place).
    These are reported as manual follow-ups at the end.

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

# Discover where the tag exists so we only delete what's there.
$localTag  = "$(git tag -l $Tag)".Trim()
$publicTag = "$(git ls-remote --tags $PublicRemote $Tag 2>$null)".Trim()
$originTag = "$(git ls-remote --tags $OriginRemote $Tag 2>$null)".Trim()

Write-Host ""
Write-Host "=== Rollback $Tag ===" -ForegroundColor Cyan
Write-Host "  Local tag      : $([bool]$localTag)"
Write-Host "  Tag on public  : $([bool]$publicTag)"
Write-Host "  Tag on origin  : $([bool]$originTag)"
Write-Host ""

if (-not ($localTag -or $publicTag -or $originTag)) {
    Write-Host "  Nothing to roll back for $Tag." -ForegroundColor Yellow
    exit 0
}

# Confirm (destructive). Require typing the version back.
if (-not $Force) {
    $confirm = Read-Host "  Delete the above $Tag tag(s)? Type the version ($Version) to confirm"
    if ($confirm -ne $Version) {
        Write-Host "  Aborted - input did not match." -ForegroundColor Yellow
        exit 1
    }
}

# Deleting the tag on public is what un-publishes the release.
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
if ($localTag) {
    Write-Host "  Deleting local tag..." -ForegroundColor Cyan
    git tag -d $Tag | Out-Null
}

Write-Host ""
Write-Host "  Rolled back $Tag." -ForegroundColor Green
Write-Host ""
Write-Host "  NOT done automatically:" -ForegroundColor DarkYellow
Write-Host "    - The GitHub Release for $Tag is now a DRAFT (deleting the tag drafts it)." -ForegroundColor Gray
Write-Host "      Re-running 'Agience: Stable - Tag Release' for $Version updates it, or" -ForegroundColor Gray
Write-Host "      delete the draft by hand from the repo's Releases page." -ForegroundColor Gray
Write-Host "    - Docker images for :$Version remain on Docker Hub + GHCR" -ForegroundColor Gray
Write-Host "      (:stable and :$MinorVersion are overwritten by the next release)." -ForegroundColor Gray
Write-Host "    - The 'Bump version to $Version' commit and the release/$MinorVersion -> main" -ForegroundColor Gray
Write-Host "      forward-port merge are left in git history." -ForegroundColor Gray
Write-Host ""
Write-Host "  Re-tag when ready:  Agience: Stable - Tag Release  (version $Version)" -ForegroundColor Gray
Write-Host ""

# Install the .githooks/ directory as git's hook path for this repo.
# Run once per checkout: .scripts\install-hooks.ps1

$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# Point git at the tracked hooks directory.
git -C $repoRoot config core.hooksPath .githooks

# On Windows, bash scripts inside .githooks/ need to be executable via git bash.
# Mark all hook scripts executable in the git index so they work after clone.
$hooks = Get-ChildItem (Join-Path $repoRoot '.githooks') -File
foreach ($hook in $hooks) {
  git -C $repoRoot update-index --chmod=+x ".githooks/$($hook.Name)" 2>$null
}

Write-Host "Git hooks installed from .githooks/ (core.hooksPath = .githooks)" -ForegroundColor Green
Write-Host "Hook scripts:" -ForegroundColor DarkGray
foreach ($hook in $hooks) {
  Write-Host "  $($hook.Name)" -ForegroundColor DarkGray
}

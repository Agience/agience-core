param([string]$Root = "C:\Users\john\Workspace\Ikailo\Repos\agience\agience-core")

$extensions = @("*.py","*.md","*.yml","*.yaml","*.bat","*.ps1","*.json","*.ts","*.tsx","*.sh","*.toml","*.cfg","*.ini","*.env","*.txt","*.caddy")

$skipPaths = @(
    "*__pycache__*",
    "*\.git\*",
    "*node_modules*",
    "*\.dev\*",
    "*_scratch*",
    "*\.claude\worktrees*",
    "*\.venv*",
    "*\.data\*",
    "*.rename_to_mantle*"
)

$files = $extensions | ForEach-Object {
    Get-ChildItem $Root -Recurse -Filter $_ -ErrorAction SilentlyContinue
} | Where-Object {
    $path = $_.FullName
    $skip = $false
    foreach ($p in $skipPaths) { if ($path -like $p) { $skip = $true; break } }
    -not $skip
} | Sort-Object FullName -Unique

Write-Host "Files to process: $(($files | Measure-Object).Count)"

# Array of [old, new] pairs -- most-specific first
$replacements = @(
    @("CollapseMantleHits",              "CollapseMantleHits"),
    @("MantleSseSearchAccessor",         "MantleSseSearchAccessor"),
    @("MantleSseSearch",                 "MantleSseSearch"),
    @("MantleQueryEngine",               "MantleQueryEngine"),
    @("MantleIndexer",                   "MantleIndexer"),
    @("MantleHit",                       "MantleHit"),
    @("agience-mantle-sse-posting-v1",   "agience-mantle-sse-posting-v1"),
    @("agience-mantle-cell-key-v1",      "agience-mantle-cell-key-v1"),
    @("MANTLE-SSE",                      "MANTLE-SSE"),
    @("MANTLE-SSE",                      "MANTLE-SSE"),
    @("MANTLE+SSE",                      "MANTLE+SSE"),
    @("MANTLE+SSE",                      "MANTLE+SSE"),
    @("MANTLE + SSE",                    "MANTLE + SSE"),
    @("MANTLE + SSE",                    "MANTLE + SSE"),
    @("MANTLE encrypted search",         "MANTLE encrypted search"),
    @("MANTLE encrypted search",         "MANTLE encrypted search"),
    @("MANTLE encrypted",                "MANTLE encrypted"),
    @("MANTLE encrypted",                "MANTLE encrypted"),
    @("MANTLE vector",                   "MANTLE vector"),
    @("MANTLE vector",                   "MANTLE vector"),
    @("MANTLE MVP",                      "MANTLE MVP"),
    @("MANTLE MVP",                      "MANTLE MVP"),
    @("MANTLE",                          "MANTLE"),
    @("MANTLE",                          "MANTLE"),
    @("VITE_MANTLE_URI",                 "VITE_MANTLE_URI"),
    @("VITE_MANTLE_URI",                 "VITE_MANTLE_URI"),
    @("MANTLE_URI",                      "MANTLE_URI"),
    @("MANTLE_URI",                      "MANTLE_URI"),
    @("mantle_changed",                  "mantle_changed"),
    @("build_mantle",                    "build_mantle"),
    @("agience-mantle",                  "agience-mantle"),
    @("agience-mantle",                  "agience-mantle"),
    @("from mantle.search",              "from mantle.search"),
    @("from mantle.services",            "from mantle.services"),
    @("from mantle.routers",             "from mantle.routers"),
    @("from mantle.entities",            "from mantle.entities"),
    @("from mantle.schemas",             "from mantle.schemas"),
    @("from mantle.db",                  "from mantle.db"),
    @("from mantle.api",                 "from mantle.api"),
    @("from mantle.tools",               "from mantle.tools"),
    @("from mantle.clients",             "from mantle.clients"),
    @("from mantle.scripts",             "from mantle.scripts"),
    @("import mantle.search",            "import mantle.search"),
    @("import mantle.services",          "import mantle.services"),
    @("import mantle.routers",           "import mantle.routers"),
    @("import mantle.entities",          "import mantle.entities"),
    @("import mantle.db",                "import mantle.db"),
    @("import mantle.api",               "import mantle.api"),
    @("import mantle",                   "import mantle"),
    @("src/mantle/",                     "src/mantle/"),
    @("src/mantle/",                     "src/mantle/"),
    @("  mantle:",                       "  mantle:"),
    @("    mantle:",                     "    mantle:"),
    @("- mantle",                        "- mantle"),
    @("Mantle (FastAPI artifact kernel)","Mantle (FastAPI artifact kernel)"),
    @("Mantle (FastAPI",                 "Mantle (FastAPI"),
    @("Mantle (governance)",             "Mantle (governance)"),
    @("ArangoDB (Mantle)",               "ArangoDB (Mantle)"),
    @("Mantle's",                        "Mantle's"),
    @("inside Mantle",                   "inside Mantle"),
    @("inside mantle",                   "inside mantle"),
    @("cdmantle/ mantle",                   "cdmantle/ mantle"),
    @("python -m mantle",                "python -m mantle"),
    @("python -m mantle",                "python -m mantle"),
    @("service: mantle",                 "service: mantle"),
    @("image: mantle",                   "image: mantle"),
    @("# Mantle",                        "# Mantle"),
    @("# mantle",                        "# mantle"),
    @("(Mantle)",                        "(Mantle)"),
    @("(mantle)",                        "(mantle)"),
    @("| mantle |",                      "| mantle |"),
    @("mantle.tools.migrate",            "mantle.tools.migrate"),
    @("mantle_client",                   "mantle_client"),
    @("src/mantle/tests",                "src/mantle/tests"),
    @("src/mantle/tests",                "src/mantle/tests"),
    @("port 8081",                      "port 8081")
)

$changed = 0
foreach ($file in $files) {
    $enc = [System.Text.Encoding]::UTF8
    try {
        $content = [System.IO.File]::ReadAllText($file.FullName, $enc)
    } catch {
        Write-Warning "  SKIP (unreadable): $($file.FullName)"
        continue
    }
    $newContent = $content
    foreach ($pair in $replacements) {
        $newContent = $newContent.Replace($pair[0], $pair[1])
    }
    if ($newContent -ne $content) {
        [System.IO.File]::WriteAllText($file.FullName, $newContent, $enc)
        Write-Host "  $($file.FullName.Replace($Root, ''))"
        $changed++
    }
}
Write-Host ""
Write-Host "Done. Files updated: $changed"

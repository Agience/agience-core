$path = 'C:\Users\john\Workspace\Ikailo\Repos\agience\my-agience-ai\docker-compose.yml'
$enc = [System.Text.Encoding]::UTF8
$content = [IO.File]::ReadAllText($path, $enc)
$pairs = @(
    @("MANTLE+SSE",           "MANTLE+SSE"),
    @("MANTLE-SSE",           "MANTLE-SSE"),
    @("MANTLE",               "MANTLE"),
    @("VITE_MANTLE_URI",      "VITE_MANTLE_URI"),
    @("MANTLE_URI",           "MANTLE_URI"),
    @("agience-mantle",       "agience-mantle"),
    @("  mantle:",            "  mantle:"),
    @("    mantle:",          "    mantle:"),
    @("# mantle",             "# mantle")
)
$new = $content
foreach ($p in $pairs) { $new = $new.Replace($p[0], $p[1]) }
[IO.File]::WriteAllText($path, $new, $enc)
Write-Host "Done"
Select-String -Path $path -Pattern 'atlas|flare|MANTLE|ATLAS' | ForEach-Object { Write-Host $_.Line.Trim() }

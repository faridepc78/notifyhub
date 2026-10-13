# NotifyHub source exporter - run from PowerShell
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$projectName = Split-Path $projectRoot -Leaf
$timestamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$zipPath = Join-Path $projectRoot "$projectName-$timestamp.zip"

$excludedDirectories = @(
    '.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.idea', '.vscode',
    'node_modules', 'staticfiles', 'media', 'exports',
    'htmlcov', 'dist', 'build', '.tox'
)
$excludedFiles = @('.env', '.env.*', '*.pyc', '*.pyo', '*.pyd', '*.sqlite3', '*.db', '*.log', '*.pem', '*.key', '*.p12', '*.pfx', '*.crt', '*.coverage*', 'coverage.xml', 'db.sqlite3', '*.zip')

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)
$count = 0
try {
    Get-ChildItem -LiteralPath $projectRoot -File -Recurse -Force | ForEach-Object {
        $file = $_
        $relative = $file.FullName.Substring($projectRoot.Length).TrimStart('\', '/')
        $segments = $relative -split '[\\/]'
        $skip = $false
        if ($segments.Length -gt 1) {
            foreach ($segment in $segments[0..($segments.Length - 2)]) {
                if ($segment -in $excludedDirectories) { $skip = $true; break }
            }
        }
        if (-not $skip) {
            foreach ($pattern in $excludedFiles) {
                if ($file.Name -like $pattern) {
                    # Allow the documented placeholder template only.
                    if ($file.Name -eq '.env.example') { continue }
                    $skip = $true
                    break
                }
            }
        }
        if (-not $skip) {
            $entryName = ($relative -replace '\\', '/')
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                $archive, $file.FullName, $entryName,
                [System.IO.Compression.CompressionLevel]::Optimal
            ) | Out-Null
            $count++
        }
    }
}
finally {
    $archive.Dispose()
}

Write-Host "Export complete: $zipPath" -ForegroundColor Green
Write-Host "Files included: $count"
Write-Host 'Review the ZIP before sharing; custom secrets in source files are not detected automatically.' -ForegroundColor Yellow

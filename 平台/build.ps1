param([ValidateSet('Current','All')][string]$Profile = 'Current')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$javaCompiler = (Get-ResearchJavaTools).Javac
New-Item -ItemType Directory -Path 'bin' -Force | Out-Null
# Clear only generated classes in this script's verified bin directory, so Current
# cannot accidentally run a stale legacy entry point from a previous All build.
$classRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'bin'))
if ((Get-Item -LiteralPath $classRoot).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw 'Build output bin must not be a junction or symbolic link.'
}
if (Get-ChildItem -LiteralPath $classRoot -Force -Recurse | Where-Object {
    $_.Attributes -band [IO.FileAttributes]::ReparsePoint
}) { throw 'Build output bin must not contain junctions or symbolic links.' }
Get-ChildItem -LiteralPath $classRoot -Filter '*.class' -File -Recurse | ForEach-Object {
    if (-not $_.FullName.StartsWith($classRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Class file escaped build output directory.'
    }
    Remove-Item -LiteralPath $_.FullName
}
$groups = @('shared','current')
if ($Profile -eq 'All') { $groups += 'legacy' }
$sources = @($groups | ForEach-Object {
    Get-Content -LiteralPath (Join-Path $PSScriptRoot "build/$_.txt") -Encoding UTF8 |
        Where-Object { $_.Trim() -and -not $_.Trim().StartsWith('#') }
})
if (($sources | Select-Object -Unique).Count -ne $sources.Count) { throw 'Duplicate source in build manifests.' }
foreach ($source in $sources) {
    if ($source -notmatch '^src/repro/[A-Za-z0-9]+\.java$' -or -not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Invalid or missing build source: $source"
    }
}
& $javaCompiler -encoding UTF-8 -source 8 -target 8 -cp 'lib/*' -d bin @sources
if ($LASTEXITCODE -ne 0) { throw 'Java compilation failed' }

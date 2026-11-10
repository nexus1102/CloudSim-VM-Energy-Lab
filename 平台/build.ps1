$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$javaCompiler = (Get-ResearchJavaTools).Javac
New-Item -ItemType Directory -Path 'bin' -Force | Out-Null
$sources = Get-ChildItem -LiteralPath 'src\repro' -Filter '*.java' | Select-Object -ExpandProperty FullName
& $javaCompiler -encoding UTF-8 -source 8 -target 8 -cp 'lib/*' -d bin @sources
if ($LASTEXITCODE -ne 0) { throw 'Java compilation failed' }

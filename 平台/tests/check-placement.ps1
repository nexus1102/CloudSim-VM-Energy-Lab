$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
. ./runtime.ps1
$tools = Get-ResearchJavaTools
& powershell -ExecutionPolicy Bypass -File ./build.ps1
if ($LASTEXITCODE -ne 0) { throw 'Current build failed' }
& $tools.Javac -encoding UTF-8 -source 8 -target 8 -cp 'bin;lib/*' -d bin tests/PlacementRegression.java
if ($LASTEXITCODE -ne 0) { throw 'Regression harness compilation failed' }
& $tools.Java -Xmx2g -cp 'bin;lib/*' repro.PlacementRegression --verify tests/placement-before-refactor.csv
if ($LASTEXITCODE -ne 0) { throw 'Placement regression failed' }

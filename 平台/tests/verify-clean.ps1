$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
. ./runtime.ps1
$tools = Get-ResearchJavaTools
$python = Get-ResearchPython
function Check-Exit { if ($LASTEXITCODE -ne 0) { throw 'Acceptance command failed' } }
& powershell -ExecutionPolicy Bypass -File ./run_research_platform.ps1 -Mode Test
Check-Exit
& powershell -ExecutionPolicy Bypass -File ./tests/check-placement.ps1
Check-Exit
& $tools.Javac -encoding UTF-8 -source 8 -target 8 -cp 'bin;lib/*' -d bin tests/MatrixAcceptance.java
Check-Exit
& $python tests/check-acceptance.py
Check-Exit
& $python tests/check-study.py $tools.Java
Check-Exit
& $python tests/check-data-package.py
Check-Exit
& $python tests/check-serialization.py $tools.Java
Check-Exit
& $python tests/check-budget-statistics.py
Check-Exit
& $python tests/check-study-inputs.py $tools.Java
Check-Exit
& $python tests/check-maintenance.py
Check-Exit
$run = 'research_platform/runs/maintenance_clean_' + [Guid]::NewGuid().ToString('N')
& powershell -ExecutionPolicy Bypass -File ./run_research_platform.ps1 -Mode Single -Method GA -Output $run
Check-Exit
& powershell -ExecutionPolicy Bypass -File ./run_research_platform.ps1 -Mode Verify -Output $run
Check-Exit
& $python tests/check-relocation.py $run
Check-Exit

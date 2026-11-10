param(
    [ValidateSet('Test','Single','Matrix','Verify')][string]$Mode = 'Test',
    [string]$Config = 'research_platform/config/default.properties',
    [string]$Output,
    [string]$Method = 'BFD-GA',
    [string]$Mapping
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$researchJava = 'H:\Company_project_study_PHD\SOFTWARE\01_JDK\jdk8u504-b01\bin\java.exe'
if (-not (Test-Path -LiteralPath $researchJava)) { $researchJava = (Get-Command java -ErrorAction Stop).Source }
$researchPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $researchPython)) { $researchPython = (Get-Command python -ErrorAction Stop).Source }
if ($Mode -ne 'Test' -and -not $Output) { throw 'Explicit -Output is required; existing runs are never overwritten.' }
& powershell -ExecutionPolicy Bypass -File build.ps1
if ($LASTEXITCODE -ne 0) { throw 'Research platform compilation failed' }
if ($Mode -eq 'Test' -or $Mode -eq 'Matrix') {
    foreach ($researchCheck in @('repro.ResearchConfig','repro.ResearchPlacement','repro.ResearchDestination','repro.ResearchRun')) {
        & $researchJava -cp 'bin;lib/*' $researchCheck
        if ($LASTEXITCODE -ne 0) { throw "Research check failed: $researchCheck" }
    }
}
if ($Mode -eq 'Test') { return }
if ($Mode -ne 'Verify') {
    $researchArguments = @('-Xmx2g','-cp','bin;lib/*','repro.ResearchExperiments','--mode',$Mode.ToLower(),'--config',$Config,'--output',$Output)
    if ($Mode -eq 'Single') {
        $researchArguments += @('--method',$Method)
        if ($Mapping) { $researchArguments += @('--mapping',$Mapping) }
    }
    & $researchJava @researchArguments
    if ($LASTEXITCODE -ne 0) { throw 'Research simulation failed; incomplete run retained for diagnosis.' }
}
if (Test-Path -LiteralPath 'tools/research_platform_report.py') {
    & $researchPython -u tools/research_platform_report.py --run $Output
    if ($LASTEXITCODE -ne 0) { throw 'Research independent audit/report failed' }
} elseif ($Mode -eq 'Verify') { throw 'Independent audit program is missing' }

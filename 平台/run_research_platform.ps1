param(
    [ValidateSet('Test','Single','Matrix','Verify')][string]$Mode = 'Test',
    [string]$Config = 'research_platform/config/default.properties',
    [string]$Output,
    [string]$Method = 'BFD-GA',
    [string]$Mapping
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$researchJava = (Get-ResearchJavaTools).Java
if ($Mode -ne 'Test' -and -not $Output) { throw 'Explicit -Output is required; existing runs are never overwritten.' }
if ($Mode -ne 'Test') {
    $researchPython = Get-ResearchPython
    if (-not (Test-Path -LiteralPath 'tools/research_platform_report.py' -PathType Leaf)) {
        throw 'Independent audit/report program is missing: tools/research_platform_report.py'
    }
}
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

# Shared environment resolution. Explicit overrides fail rather than silently falling back.
function Get-ResearchJavaTools {
    $javaHome = $env:RESEARCH_JAVA_HOME
    if (-not $javaHome) { $javaHome = $env:JAVA_HOME }
    if ($javaHome) {
        $java = Join-Path $javaHome 'bin/java.exe'
        $javac = Join-Path $javaHome 'bin/javac.exe'
    } else {
        $compiler = Get-Command javac -ErrorAction SilentlyContinue
        if ($compiler) {
            $javac = $compiler.Source
            $java = Join-Path (Split-Path -Parent $javac) 'java.exe'
        } else {
            # Compatibility fallback for the original workstation; never used ahead of PATH.
            $javaHome = 'H:\Company_project_study_PHD\SOFTWARE\01_JDK\jdk8u504-b01'
            $java = Join-Path $javaHome 'bin/java.exe'
            $javac = Join-Path $javaHome 'bin/javac.exe'
        }
    }
    foreach ($executable in @($java, $javac)) {
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
            throw "JDK is incomplete: $executable. Set RESEARCH_JAVA_HOME to a JDK 8 directory."
        }
    }
    return @{ Java = $java; Javac = $javac }
}

function Get-ResearchPython {
    $candidates = @()
    if ($env:RESEARCH_PYTHON) { $candidates = @($env:RESEARCH_PYTHON) }
    else {
        $candidates += Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
        $command = Get-Command python -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
        $candidates += Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        & $candidate -c 'import sys; assert sys.version_info >= (3, 10); import numpy, matplotlib, PIL' 2>$null
        if ($LASTEXITCODE -eq 0) { return $candidate }
    }
    throw 'No compatible Python found. Set RESEARCH_PYTHON to Python >=3.10 with requirements.txt installed (python -m pip install -r requirements-lock.txt).'
}

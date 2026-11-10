$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$javaCompiler = 'H:\Company_project_study_PHD\SOFTWARE\01_JDK\jdk8u504-b01\bin\javac.exe'
if (-not (Test-Path -LiteralPath $javaCompiler)) { $javaCompiler = (Get-Command javac -ErrorAction Stop).Source }
New-Item -ItemType Directory -Path 'bin' -Force | Out-Null
$sources = Get-ChildItem -LiteralPath 'src\repro' -Filter '*.java' | Select-Object -ExpandProperty FullName
& $javaCompiler -encoding UTF-8 -source 8 -target 8 -cp 'lib/*' -d bin @sources
if ($LASTEXITCODE -ne 0) { throw 'Java compilation failed' }

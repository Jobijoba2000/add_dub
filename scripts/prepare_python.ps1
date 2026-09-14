$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$projectRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $projectRoot 'tools\python'
if (Test-Path -LiteralPath (Join-Path $target 'python.exe')) { exit 0 }
$cache = Join-Path $projectRoot '.cache'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
$archive = Join-Path $cache 'python.3.12.3.zip'
$expected = '03c935cd2f2eceb7de3cfb2eb98e163ab21eec12dce78eb833d15bc4dd3ecbf3'
$work = Join-Path $cache ('python-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
try {
    if (!(Test-Path -LiteralPath $archive) -or (Get-FileHash -LiteralPath $archive).Hash -ne $expected) {
        Write-Host '[Python] Telechargement de Python 3.12.3 x64...'
        $download = Join-Path $work 'python.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://api.nuget.org/v3-flatcontainer/python/3.12.3/python.3.12.3.nupkg' -OutFile $download
        if ((Get-FileHash -LiteralPath $download).Hash -ne $expected) { throw 'Empreinte Python incorrecte.' }
        Move-Item -LiteralPath $download -Destination $archive -Force
    }
    Write-Host '[Python] Extraction...'
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $work 'package')
    $extracted = Join-Path $work 'package\tools'
    & (Join-Path $extracted 'python.exe') -I -c 'import venv, ensurepip, ssl'
    if ($LASTEXITCODE -ne 0) { throw 'Verification Python en echec.' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    if (Test-Path -LiteralPath $target) {
        throw 'tools/python existe mais est incomplet. Conservez-le sous un autre nom avant de relancer.'
    }
    Move-Item -LiteralPath $extracted -Destination $target
    Write-Host '[Python] Pret.'
} finally {
    # Nettoyage exclusivement du dossier temporaire cree ci-dessus.
    $resolvedWork = [IO.Path]::GetFullPath($work)
    if (!$resolvedWork.StartsWith([IO.Path]::GetFullPath($cache) + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Chemin temporaire inattendu.'
    }
    Remove-Item -LiteralPath $resolvedWork -Recurse -Force
}

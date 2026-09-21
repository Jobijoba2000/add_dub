$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$downloadUrl = 'https://aka.ms/vc14/vc_redist.x64.exe'

function Test-VCRuntime {
    # Lecture explicite de la vue x64, meme depuis PowerShell 32 bits.
    $registry = [Microsoft.Win32.RegistryKey]::OpenBaseKey('LocalMachine', 'Registry64')
    try {
        $key = $registry.OpenSubKey('SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64')
        if (!$key) { return $false }
        try {
            if ($key.GetValue('Installed', 0) -ne 1) { return $false }
        } finally { $key.Dispose() }
    } finally { $registry.Dispose() }
    $systemDir = Join-Path $env:WINDIR 'System32'
    if (![Environment]::Is64BitProcess) { $systemDir = Join-Path $env:WINDIR 'Sysnative' }
    foreach ($dll in @('vcruntime140.dll', 'vcruntime140_1.dll', 'msvcp140.dll')) {
        if (!(Test-Path -LiteralPath (Join-Path $systemDir $dll))) { return $false }
    }
    return $true
}

try {
    if (![Environment]::Is64BitOperatingSystem) { throw 'add_dub necessite Windows 64 bits.' }
    if (Test-VCRuntime) {
        Write-Host '[Visual C++] Runtime x64 present.'
        exit 0
    }
    Write-Host '[Visual C++] Microsoft Visual C++ Redistributable x64 est absent ou incomplet.'
    Write-Host '[Visual C++] Ce composant Windows est necessaire au chargement de CTranslate2.'
    Write-Host '[Visual C++] Telechargement depuis Microsoft...'
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $cache = Join-Path (Split-Path -Parent $PSScriptRoot) '.cache'
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    $installer = Join-Path $cache ('vc_redist-' + [guid]::NewGuid().ToString('N') + '.x64.exe')
    Invoke-WebRequest -UseBasicParsing -Uri $downloadUrl -OutFile $installer
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation(?:,|$)') {
        throw 'Signature Microsoft de l''installeur invalide. Installation annulee.'
    }
    Write-Host '[Visual C++] Installation : acceptez la demande administrateur Windows si elle apparait.'
    $process = Start-Process -FilePath $installer -ArgumentList '/install', '/quiet', '/norestart' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -eq 3010) {
        throw 'Installation terminee, mais un redemarrage Windows est requis. Redemarrez puis relancez start_add_dub.bat.'
    }
    if ($process.ExitCode -ne 0) { throw "Echec de l'installation (code $($process.ExitCode))." }
    if (!(Test-VCRuntime)) { throw 'Le runtime reste introuvable apres installation.' }
    Write-Host '[Visual C++] Installation terminee. Reprise de la preparation d''add_dub.'
} catch {
    Write-Host "[ERREUR] $($_.Exception.Message)"
    Write-Host "[AIDE] Installez/reparez Microsoft Visual C++ Redistributable x64 : $downloadUrl"
    Write-Host '[AIDE] Puis relancez start_add_dub.bat. Une autorisation administrateur peut etre necessaire.'
    exit 1
}

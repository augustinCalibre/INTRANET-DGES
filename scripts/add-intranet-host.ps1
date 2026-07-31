param(
    [string]$ServerIp = "192.168.100.5"
)

$hostsPath = "C:\Windows\System32\drivers\etc\hosts"
$entries = @(
    "$ServerIp intranet-dges.local",
    "$ServerIp messagerie.dges.local"
)

$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Write-Error "Ce script doit etre execute en tant qu'administrateur."
    exit 1
}

if (-not (Test-Path $hostsPath)) {
    Write-Error "Fichier hosts introuvable: $hostsPath"
    exit 1
}

$content = Get-Content $hostsPath -ErrorAction Stop
foreach ($entry in $entries) {
    if ($content -contains $entry) {
        Write-Host "Entree deja presente: $entry"
    } else {
        Add-Content -Path $hostsPath -Value "`r`n$entry" -ErrorAction Stop
        Write-Host "Entree ajoutee: $entry"
    }
}

ipconfig /flushdns | Out-Null
Write-Host "Cache DNS vide."
Write-Host "Verification:"
ping intranet-dges.local -n 1
ping messagerie.dges.local -n 1

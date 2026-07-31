[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$rules = @(
    @{ Name = "Intranet DGES HTTP"; Port = 80 },
    @{ Name = "Intranet DGES HTTPS"; Port = 443 },
    @{ Name = "Intranet DGES Talk"; Port = 8443 }
)

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Regle deja presente : $($rule.Name)" -ForegroundColor Yellow
        continue
    }

    New-NetFirewallRule `
        -DisplayName $rule.Name `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $rule.Port | Out-Null

    Write-Host "Regle creee : $($rule.Name) (TCP/$($rule.Port))" -ForegroundColor Green
}

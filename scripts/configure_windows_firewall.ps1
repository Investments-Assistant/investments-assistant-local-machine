[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $false)]
    [ValidatePattern('^[0-9]{1,3}(\.[0-9]{1,3}){3}/([0-9]|[12][0-9]|3[0-2])$')]
    [string]$LanCidr = '192.168.1.0/24',

    [Parameter(Mandatory = $false)]
    [int[]]$Ports = @(8080, 8443),

    [Parameter(Mandatory = $false)]
    [switch]$SkipProfileEnforcement
)

$ErrorActionPreference = 'Stop'
$group = 'Investment Assistant LAN'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell window (Run as administrator).'
}

if (-not $SkipProfileEnforcement) {
    # Keep inbound traffic closed by default. The two narrow allow rules below
    # are the only intended exception for this application.
    if ($PSCmdlet.ShouldProcess('Windows Defender Firewall profiles', 'Enable and set default inbound action to Block')) {
        Set-NetFirewallProfile -Profile Domain,Private,Public `
            -Enabled True -DefaultInboundAction Block -DefaultOutboundAction Allow
    }
}

if ($PSCmdlet.ShouldProcess("firewall rule group '$group'", 'Replace application rules')) {
    Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule

    foreach ($port in $Ports) {
        New-NetFirewallRule `
            -Name "InvestmentAssistant-LAN-$port" `
            -DisplayName "Investment Assistant LAN TCP $port" `
            -Group $group `
            -Description "Allow Investment Assistant TCP $port only from $LanCidr; edge traversal blocked." `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $port `
            -RemoteAddress $LanCidr `
            -Profile Any `
            -EdgeTraversalPolicy Block |
            Out-Null
    }
}

# Docker Desktop may install a broad Public-profile allow rule for its backend.
# Scope that existing rule to the same LAN so it cannot bypass the application
# rules above when Docker forwards a published port before it reaches Nginx.
$dockerBackendRules = @(Get-NetFirewallRule -DisplayName 'Docker Desktop Backend' -ErrorAction SilentlyContinue)
foreach ($rule in $dockerBackendRules) {
    if ($PSCmdlet.ShouldProcess($rule.DisplayName, "Restrict remote addresses to $LanCidr")) {
        Set-NetFirewallRule -Name $rule.Name -RemoteAddress $LanCidr -EdgeTraversalPolicy Block
    }
}

$profiles = Get-NetFirewallProfile -Profile Domain,Private,Public
$invalidProfiles = $profiles | Where-Object {
    -not $_.Enabled -or $_.DefaultInboundAction -ne 'Block'
}
if ($invalidProfiles) {
    throw 'Windows Firewall is not enabled with default inbound Block on every profile.'
}

$rules = @(Get-NetFirewallRule -Group $group -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' })
if ($rules.Count -ne $Ports.Count) {
    throw "Expected $($Ports.Count) enabled LAN allow rules, found $($rules.Count)."
}

Write-Host "Windows Firewall ready: TCP $($Ports -join ', ') allowed only from $LanCidr; default inbound traffic is blocked."

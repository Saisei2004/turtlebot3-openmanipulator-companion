# 管理者の PowerShell で動かす。WSL（mirrored ネットワーク）に、LAN から ROS 2 (DDS) の通信と操作画面への受信を許す。
# 許すのは「ローカルサブネットからだけ」。既定の Hyper-V ファイアウォールは、WSL への外からの受信を全部止めるので、これが無いと機体が PC に届かない。
#
# 使い方:  .\allow_wsl_ros2_firewall.ps1 [-DomainId 0] [-WebPorts 8080,9090] [-Remove]
#   -DomainId  ROS_DOMAIN_ID（DDS のポートは 7400 + 250 × ID から 250 個）
#   -Remove    このスクリプトが作った規則を消す
param([int]$DomainId = 0, [int[]]$WebPorts = @(8080, 9090), [switch]$Remove)
$ErrorActionPreference = 'Stop'
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { Write-Host '管理者として実行されていません。何も変更していません'; Read-Host 'Enter で閉じる'; exit 1 }
$names = 'TB3-DDS-UDP-HyperV', 'TB3-Web-HyperV', 'TB3-DDS-UDP-Host', 'TB3-Web-Host'
if ($Remove) {
  foreach ($n in 'TB3-DDS-UDP-HyperV', 'TB3-Web-HyperV') { Remove-NetFirewallHyperVRule -Name $n -ErrorAction SilentlyContinue }
  foreach ($n in 'TB3-DDS-UDP-Host', 'TB3-Web-Host') { Remove-NetFirewallRule -Name $n -ErrorAction SilentlyContinue }
  Write-Host '規則を消しました'; Read-Host 'Enter で閉じる'; exit 0
}
$vm = '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}'   # WSL の VM の固定 ID
$sub = 'LocalSubnet'
$lo = 7400 + 250 * $DomainId; $hi = $lo + 249
$udp = "$lo-$hi"
foreach ($n in $names) { Remove-NetFirewallHyperVRule -Name $n -ErrorAction SilentlyContinue; Remove-NetFirewallRule -Name $n -ErrorAction SilentlyContinue }
New-NetFirewallHyperVRule -Name 'TB3-DDS-UDP-HyperV' -DisplayName "TB3 ROS2 DDS (UDP $udp)" -Direction Inbound -VMCreatorId $vm -Protocol UDP -LocalPorts $udp -RemoteAddresses $sub -Action Allow | Out-Null
New-NetFirewallHyperVRule -Name 'TB3-Web-HyperV' -DisplayName "TB3 Web (TCP $($WebPorts -join ','))" -Direction Inbound -VMCreatorId $vm -Protocol TCP -LocalPorts $WebPorts -RemoteAddresses $sub -Action Allow | Out-Null
New-NetFirewallRule -Name 'TB3-DDS-UDP-Host' -DisplayName "TB3 ROS2 DDS (UDP $udp)" -Direction Inbound -Protocol UDP -LocalPort $udp -RemoteAddress $sub -Action Allow -Profile Any | Out-Null
New-NetFirewallRule -Name 'TB3-Web-Host' -DisplayName "TB3 Web (TCP $($WebPorts -join ','))" -Direction Inbound -Protocol TCP -LocalPort $WebPorts -RemoteAddress $sub -Action Allow -Profile Any | Out-Null
Get-NetFirewallHyperVRule -Name 'TB3-*' | Format-Table Name, Direction, Action, Protocol, LocalPorts
Get-NetFirewallRule -Name 'TB3-*' | Format-Table Name, Enabled, Action
Write-Host "OK: 追加しました（UDP $udp, TCP $($WebPorts -join ',')）"
Read-Host 'Enter で閉じる'

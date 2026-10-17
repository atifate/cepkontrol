$ErrorActionPreference = 'Stop'
Restart-Service -Name Tailscale -ErrorAction Stop

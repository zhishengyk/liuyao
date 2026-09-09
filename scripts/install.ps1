param(
    [string]$Python = 'py',
    [switch]$RegisterMcp,
    [switch]$InstallPlugin,
    [switch]$SkipBuild
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskVenv = Join-Path $taskRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $taskRoot
try {
    if (-not (Test-Path -LiteralPath $taskVenv)) {
        if ($Python -eq 'py') { & $Python -3.11 -m venv .venv }
        else { & $Python -m venv .venv }
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed' }
    }
    & $taskVenv -m pip install --disable-pip-version-check -e '.[test]'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    $env:PYTHONIOENCODING = 'utf-8'
    $env:LIUYAO_ROOT = $taskRoot
    if (-not $SkipBuild) {
        & $taskVenv -m liuyao_mcp.ingest
        if ($LASTEXITCODE -ne 0) { throw 'Knowledge import failed' }
    }
    $taskLocal = Join-Path $taskRoot '.local'
    New-Item -ItemType Directory -Path $taskLocal -Force | Out-Null
    $taskConfig = @"
[mcp_servers.liuyao]
command = '$taskVenv'
args = ['-m', 'liuyao_mcp.server']
cwd = '$taskRoot'
startup_timeout_sec = 30

[mcp_servers.liuyao.env]
LIUYAO_ROOT = '$taskRoot'
PYTHONIOENCODING = 'utf-8'

[mcp_servers.liuyao.tools.search_knowledge]
output_token_limit = 60000

[mcp_servers.liuyao.tools.get_source]
output_token_limit = 60000
"@
    [System.IO.File]::WriteAllText((Join-Path $taskLocal 'mcp-config.toml'), $taskConfig, [System.Text.UTF8Encoding]::new($false))
    if ($RegisterMcp) {
        # codex mcp add changes only the named server, preserving other configuration.
        & codex mcp add liuyao --env "LIUYAO_ROOT=$taskRoot" --env 'PYTHONIOENCODING=utf-8' -- $taskVenv -m liuyao_mcp.server
        if ($LASTEXITCODE -ne 0) { throw 'MCP registration failed' }
        & $taskVenv -X utf8 scripts/configure_output_budget.py
        if ($LASTEXITCODE -ne 0) { throw 'MCP output budget configuration failed' }
    }
    if ($InstallPlugin) {
        & $taskVenv -X utf8 scripts/install_plugin.py
        if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed' }
    }
    Write-Output 'Installation complete. MCP configuration: .local/mcp-config.toml'
} finally {
    Pop-Location
}

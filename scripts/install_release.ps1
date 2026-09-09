$ErrorActionPreference = 'Stop'
Get-Command codex -ErrorAction Stop | Out-Null
Get-Command uvx -ErrorAction Stop | Out-Null
Push-Location -LiteralPath ([System.IO.Path]::GetTempPath())
try {
    $taskCatalog = codex plugin marketplace list --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read Codex marketplaces' }
    if (-not ($taskCatalog.marketplaces | Where-Object name -eq 'liuyao')) {
        & codex plugin marketplace add zhishengyk/liuyao --ref main --sparse .agents/plugins --sparse plugins/liuyao-assistant
        if ($LASTEXITCODE -ne 0) { throw 'Cannot add GitHub marketplace' }
    } else {
        & codex plugin marketplace upgrade liuyao
        if ($LASTEXITCODE -ne 0) { throw 'Cannot refresh marketplace; installed plugin is unchanged' }
    }
    $taskCatalog = codex plugin marketplace list --json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read refreshed marketplace' }
    $taskMarket = $taskCatalog.marketplaces | Where-Object name -eq 'liuyao' | Select-Object -First 1
    $taskConfig = Get-Content -Raw -Encoding UTF8 (Join-Path $taskMarket.root 'plugins/liuyao-assistant/.mcp.json') | ConvertFrom-Json
    $taskServer = $taskConfig.mcpServers.liuyao
    if ($taskServer.command -ne 'uvx') { throw 'Unsupported release launcher' }
    $taskPrepareArgs = @($taskServer.args | Where-Object { $_ -ne '--offline' })
    & uvx @taskPrepareArgs --version
    if ($LASTEXITCODE -ne 0) { throw 'Release preparation failed; installed plugin is unchanged' }
    $taskOfflineArgs = @($taskServer.args)
    & uvx @taskOfflineArgs --self-check
    if ($LASTEXITCODE -ne 0) { throw 'Offline self-check failed; installed plugin is unchanged' }
    & codex plugin add liuyao-assistant@liuyao --json
    if ($LASTEXITCODE -ne 0) { throw 'Plugin installation failed' }
    Write-Output 'Liuyao installed. Start a new Codex session. Daily retrieval runs offline.'
} finally {
    Pop-Location
}

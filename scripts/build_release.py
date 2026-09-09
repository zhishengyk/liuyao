"""Build a self-contained release from the source manifest, never a local model index."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys
import zipfile

from liuyao_mcp import __version__
from liuyao_mcp.ingest import ingest


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / ".local/release-data/knowledge.sqlite"
    ingest(root, output)
    bundled = root / "src/liuyao_mcp/_data/knowledge.sqlite"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, bundled)
    subprocess.run([sys.executable, "-m", "build"], cwd=root, check=True)
    dist = root / "dist"
    archive = dist / f"liuyao_mcp-{__version__}.tar.gz"
    shutil.copy2(archive, dist / "liuyao-mcp.tar.gz")
    artifacts = [archive, dist / f"liuyao_mcp-{__version__}-py3-none-any.whl", dist / "liuyao-mcp.tar.gz"]
    plugin = root / 'plugins/liuyao-assistant'
    import json
    manifest = json.loads((plugin/'.codex-plugin/plugin.json').read_text(encoding='utf8'))
    assert manifest['version'] == __version__, 'Plugin and package versions differ'
    config = json.loads((plugin/'.mcp.json').read_text(encoding='utf8'))
    assert f'https://github.com/zhishengyk/liuyao/releases/download/v{__version__}/liuyao_mcp-{__version__}-py3-none-any.whl' in config['mcpServers']['liuyao']['args']
    plugin_archive = dist / f'liuyao-plugin-{__version__}.zip'
    with zipfile.ZipFile(plugin_archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(plugin.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(root).as_posix())
        bundle.write(root/'.agents/plugins/marketplace.json', '.agents/plugins/marketplace.json')
        bundle.write(root/'scripts/install_release.ps1', 'install.ps1')
    installer = dist/'install.ps1'
    shutil.copy2(root/'scripts/install_release.ps1', installer)
    artifacts += [plugin_archive, installer]
    (dist / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in artifacts), encoding="utf8")


if __name__ == "__main__":
    main()

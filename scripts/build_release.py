"""Build a self-contained release from the source manifest, never a local model index."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import zipfile

from liuyao_mcp import __version__
from liuyao_mcp.ingest import ingest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-corpus-hash", help="Require the validated source snapshot before packaging")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / ".local/release-data/knowledge.sqlite"
    report = ingest(root, output)
    if args.expected_corpus_hash and report['corpus_hash'] != args.expected_corpus_hash:
        raise ValueError('Source or parser changed since validation; release was not built')
    with sqlite3.connect(output) as db:
        assert db.execute('SELECT count(*) FROM eval_items').fetchone()[0] == 0
        assert not db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'vec_%'").fetchall()
        metadata = {
            'version': __version__, 'corpus_hash': report['corpus_hash'],
            'database_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'build_info': dict(db.execute('SELECT key,value FROM build_info')),
            'counts': {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                       for table in ('sources', 'chunks', 'cases', 'ocr_edits')},
            'ocr_review': report['ocr_review'],
            'sources': [json.loads(row[0]) for row in db.execute('SELECT metadata FROM sources ORDER BY id')],
            'retrieval_default': 'bm25', 'includes_model_weights': False,
        }
    bundled = root / "src/liuyao_mcp/_data/knowledge.sqlite"
    bundled.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, bundled)
    subprocess.run([sys.executable, "-m", "build"], cwd=root, check=True)
    dist = root / "dist"
    archive = dist / f"liuyao_mcp-{__version__}.tar.gz"
    shutil.copy2(archive, dist / "liuyao-mcp.tar.gz")
    artifacts = [archive, dist / f"liuyao_mcp-{__version__}-py3-none-any.whl", dist / "liuyao-mcp.tar.gz"]
    plugin = root / 'plugins/liuyao-assistant'
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
    wheel = dist / f"liuyao_mcp-{__version__}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as bundle:
        assert hashlib.sha256(bundle.read('liuyao_mcp/_data/knowledge.sqlite')).hexdigest() == metadata['database_sha256']
        assert not any('evaluation/' in name or name.endswith(('.npz', '.safetensors')) for name in bundle.namelist())
    release_manifest = dist / 'release-manifest.json'
    release_manifest.write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
    artifacts.append(release_manifest)
    (dist / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in artifacts), encoding="utf8")
    print(json.dumps({'version': __version__, 'corpus_hash': report['corpus_hash'],
                      'counts': metadata['counts'], 'artifacts': [p.name for p in artifacts]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

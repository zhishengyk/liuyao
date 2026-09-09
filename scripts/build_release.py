"""Build a self-contained release from the source manifest, never a local model index."""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

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
    (dist / "SHA256SUMS").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in artifacts), encoding="utf8")


if __name__ == "__main__":
    main()

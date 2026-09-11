"""Check that URLs emitted by Vite resolve to real production assets."""
from pathlib import Path
import re
from urllib.parse import unquote

root = Path(__file__).resolve().parents[1]
dist = root / "frontend" / "dist"
index = dist / "index.html"
assert index.is_file(), "Run npm run build first."
sources = [index, *dist.glob("assets/*.js"), *dist.glob("assets/*.css")]
urls = set()
for source in sources:
    urls.update(re.findall(r'''["'](/assets/[^"']+)["']''', source.read_text(encoding="utf-8")))
assert urls, "No bundled assets were found."
missing = [url for url in urls if not (dist / unquote(url.lstrip("/"))).is_file()]
assert not missing, f"Missing production assets: {missing}"
images = [path for path in (root / "assets").rglob("*") if path.is_file()]
assert images, "Source image catalog is missing."
for source in images:
    target = dist / source.relative_to(root / "assets")
    assert target.is_file(), f"Missing public image: {target}"
    assert source.stat().st_size == target.stat().st_size, f"Incomplete public image: {target}"
print(f"PASS: {len(urls)} bundled URLs resolve and {len(images)} public images were copied.")

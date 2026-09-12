"""Refresh the compact Data Dragon names and image map (no Riot API key).

Normal builds and browser startup use the saved map and never run this script.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CDN = "https://ddragon.leagueoflegends.com"
CACHE_DIR = ROOT / "data" / "cache" / "ddragon"
OUTPUT = ROOT / "frontend" / "src" / "riot-assets.json"
CACHE_TTL = 86400


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def fetch_json(url, *, force=False, cache_dir=CACHE_DIR):
    path = cache_dir / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    if not force:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached["url"] == url and 0 <= time.time() - cached["fetchedAt"] < CACHE_TTL:
                return cached["value"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "TFTLOL-assets/1"})
    with urlopen(request, timeout=15) as response:
        value = json.load(response)
    write_json(path, {"url": url, "fetchedAt": time.time(), "value": value})
    return value


def image_name(row):
    filename = row["image"]["full"]
    if not isinstance(filename, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+\.png", filename):
        raise ValueError("Unexpected Data Dragon image filename.")
    return filename


def display_name(row):
    name = row["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Missing Data Dragon display name.")
    return name


def make_manifest(version, champions, tft_champions, tft_regalia, items, rune_styles):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Version must be a Data Dragon version such as 16.18.1.")
    lol = {row["key"]: image_name(row) for row in champions["data"].values()}
    # Current TFT JSON keys are internal asset paths. Match history uses row.id.
    tft = {row["id"]: image_name(row) for row in tft_champions["data"].values()}
    ranks = {tier.upper(): image_name(row)
             for tier, row in tft_regalia["data"]["RANKED_TFT"].items()}
    champion_names = {row["key"]: display_name(row) for row in champions["data"].values()}
    # Riot includes unnamed placeholder items in otherwise valid catalogs.
    item_names = {key: display_name(row) if row.get("name") else f"Item {key}"
                  for key, row in items["data"].items()}
    runes = {}
    for style in rune_styles:
        for row in [style, *(rune for slot in style["slots"] for rune in slot["runes"])]:
            icon = row["icon"]
            if not isinstance(icon, str) or not re.fullmatch(
                    r"perk-images/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.png", icon):
                raise ValueError("Unexpected Data Dragon rune image path.")
            runes[str(row["id"])] = {"name": display_name(row), "icon": icon}
    if not lol or not tft or "GOLD" not in ranks or any(not key.isdigit() for key in lol):
        raise ValueError("Incomplete Data Dragon metadata; keeping the previous filename map.")
    if not item_names or not runes or any(not key.isdigit() for key in (*item_names, *runes)):
        raise ValueError("Incomplete item or rune metadata.")
    return {"schemaVersion": 2, "version": version,
            "champions": dict(sorted(lol.items())),
            "championNames": dict(sorted(champion_names.items())),
            "itemNames": dict(sorted(item_names.items())),
            "runes": dict(sorted(runes.items())),
            "tftChampions": dict(sorted(tft.items())),
            "tftRegalia": dict(sorted(ranks.items()))}


def update_assets(version=None, *, force=False, cache_dir=CACHE_DIR, output=OUTPUT):
    if version is None:
        versions = fetch_json(f"{CDN}/api/versions.json", force=force, cache_dir=cache_dir)
        if not isinstance(versions, list) or not versions:
            raise ValueError("Data Dragon returned an empty version list.")
        version = versions[0]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid Data Dragon version.")
    urls = [f"{CDN}/cdn/{version}/data/en_US/{name}.json"
            for name in ("champion", "tft-champion", "tft-regalia", "item", "runesReforged")]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fetch_json, url, force=force, cache_dir=cache_dir) for url in urls]
        payloads = [future.result() for future in futures]
    manifest = make_manifest(version, *payloads)
    # Publish only after every category was downloaded and validated successfully.
    write_json(output, manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Pin a specific patch; default: latest published version")
    parser.add_argument("--force", action="store_true", help="Bypass the 24-hour metadata download cache")
    args = parser.parse_args()
    try:
        manifest = update_assets(args.version, force=args.force)
    except Exception as error:
        parser.exit(1, f"Asset update failed; the existing filename map is unchanged: {error}\n")
    print(f"Saved Data Dragon {manifest['version']}: {len(manifest['champions'])} LoL champions, "
          f"{len(manifest['tftChampions'])} TFT units, {len(manifest['tftRegalia'])} TFT ranks, "
          f"{len(manifest['itemNames'])} item names, {len(manifest['runes'])} rune/style names.")


if __name__ == "__main__":
    main()

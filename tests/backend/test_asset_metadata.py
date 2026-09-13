from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import update_assets as updater


def fixtures():
    return [
        {"data": {"Aatrox": {"key": "266", "name": "Aatrox", "image": {"full": "Aatrox.png"}}}},
        {"data": {"Maps/Shipping/Map22/Shop/TFT18_Zed": {
            "id": "TFT18_Zed", "image": {"full": "TFT18_Zed.TFT_Set18.png"}}}},
        {"data": {"RANKED_TFT": {
            "Gold": {"image": {"full": "TFT_Regalia_Gold.png"}},
            "Grandmaster": {"image": {"full": "TFT_Regalia_GrandMaster.png"}}}}},
        {"data": {"1001": {"name": "Boots"}, "2008": {"name": ""}}},
        [{"id": 8000, "name": "Precision", "icon": "perk-images/Styles/7201_Precision.png",
          "slots": [{"runes": [{"id": 8005, "name": "Press the Attack",
                                "icon": "perk-images/Styles/Precision/PressTheAttack/PressTheAttack.png"}]}]}],
    ]


class AssetMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_mapping_uses_lol_numeric_keys_and_tft_character_ids(self):
        result = updater.make_manifest("16.18.1", *fixtures())
        self.assertEqual({"266": "Aatrox.png"}, result["champions"])
        self.assertEqual({"TFT18_Zed": "TFT18_Zed.TFT_Set18.png"}, result["tftChampions"])
        self.assertEqual("TFT_Regalia_GrandMaster.png", result["tftRegalia"]["GRANDMASTER"])
        self.assertEqual("Aatrox", result["championNames"]["266"])
        self.assertEqual("Boots", result["itemNames"]["1001"])
        self.assertEqual("Item 2008", result["itemNames"]["2008"])
        self.assertEqual("Press the Attack", result["runes"]["8005"]["name"])
        invalid = fixtures()
        invalid[0]["data"]["Aatrox"]["image"]["full"] = "../../secret.png"
        with self.assertRaises(ValueError):
            updater.make_manifest("16.18.1", *invalid)

    def test_download_cache_expires_and_force_refresh_bypasses_it(self):
        url = updater.CDN + "/api/versions.json"
        values = [["16.18.1"], ["16.18.2"], ["16.18.3"]]
        with patch.object(updater, "urlopen", side_effect=[
                BytesIO(json.dumps(value).encode()) for value in values]) as download:
            with patch.object(updater.time, "time", return_value=100):
                self.assertEqual(values[0], updater.fetch_json(url, cache_dir=self.root))
                self.assertEqual(values[0], updater.fetch_json(url, cache_dir=self.root))
                self.assertEqual(1, download.call_count)
            with patch.object(updater.time, "time", return_value=100 + updater.CACHE_TTL):
                self.assertEqual(values[1], updater.fetch_json(url, cache_dir=self.root))
                self.assertEqual(values[2], updater.fetch_json(url, cache_dir=self.root, force=True))
                self.assertEqual(3, download.call_count)
        request = download.call_args.args[0]
        self.assertIsNone(request.get_header("X-riot-token"))

    def test_bad_json_is_not_cached(self):
        with patch.object(updater, "urlopen", return_value=BytesIO(b"broken")):
            with self.assertRaises(ValueError):
                updater.fetch_json(updater.CDN + "/bad.json", cache_dir=self.root)
        self.assertEqual([], list(self.root.glob("*.json")))

    def test_failed_metadata_update_preserves_last_working_manifest(self):
        output = self.root / "manifest.json"
        original = b'{"version":"previous-working-version"}\n'
        output.write_bytes(original)
        with patch.object(updater, "fetch_json", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                updater.update_assets("16.18.1", output=output)
        self.assertEqual(original, output.read_bytes())
        payloads = dict(zip(("champion", "tft-champion", "tft-regalia", "item", "runesReforged"), fixtures()))

        def download(url, **kwargs):
            return payloads[Path(url).stem]

        with patch.object(updater, "fetch_json", side_effect=download):
            result = updater.update_assets("16.18.1", output=output)
        self.assertEqual(result, json.loads(output.read_text(encoding="utf-8")))

    def test_invalid_rune_path_or_missing_names_preserve_previous_manifest(self):
        output = self.root / "manifest.json"
        original = '{"version":"previous"}'
        for field in ("name", "icon"):
            payloads = dict(zip(("champion", "tft-champion", "tft-regalia", "item", "runesReforged"), fixtures()))
            payloads["runesReforged"][0][field] = "" if field == "name" else "perk-images/../secret.png"
            output.write_text(original, encoding="utf-8")
            with patch.object(updater, "fetch_json", side_effect=lambda url, **kwargs: payloads[Path(url).stem]):
                with self.assertRaises(ValueError):
                    updater.update_assets("16.18.1", output=output)
            self.assertEqual(original, output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

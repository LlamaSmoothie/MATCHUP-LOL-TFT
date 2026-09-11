# Archive

This directory preserves files that are not needed to run or build the current
React/Python web application. Nothing was discarded during reorganization.

| Location | Preserved contents |
| --- | --- |
| `desktop/` | Original Qt application, generated UI, Qt Designer file, chart utility, game metadata helper, SearchMatch adapter, dependency list, and win-rate image |
| `desktop/data/` | Old rune and TFT JSON snapshots unused by the current web backend |
| `desktop/picture/` | Screenshots and older UI artwork unused by React |
| `experiments/project2.py` | Older generated UI prototype, including its pre-existing unresolved merge-conflict markers |
| `experiments/get_data_from_website.py` | Historical downloader with network/write side effects; not executed by the current app or checks |
| `generated/previous-dist/` | Complete production build that existed before reorganization |
| `generated/before-load-optimization-dist/` | Production build preserved before replacing the eager image imports |
| `generated/root-pycache/`, `generated/test-pycache/` | Previously generated Python bytecode |
| `logs/` | Previous Vite development logs |

`generated/` and `logs/` remain on disk and are ignored by Git. Archiving them
does not make them current build artifacts: new builds go to `frontend/dist/`.

The historical Qt screens are reference material, not a supported web-app entry
point. They still contain old relative image/data paths and version-specific TFT
presentation code. Their local artwork is preserved here; images also used by
React are in root `assets/`, and active queue/spell JSON is in `data/static/`.
The lightweight `desktop/searchMatch.py` adapter has updated backend imports and
remains covered by the offline tests without requiring PyQt.

The active application starts from the repository root with `npm run backend`
and `npm run dev`. Neither command loads these archived screens or experiments.

## Move record

`move-manifest.json` records the chronological moves and the number of files
whose SHA-256 hashes were verified at each move. Some directories were moved
before their contents were organized further; follow subsequent entries for
the final destination. Import/configuration/documentation edits were made after
the file-preservation checks.

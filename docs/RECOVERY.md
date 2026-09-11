# Restore the local-image application

The state immediately before the Riot CDN migration is saved in an annotated
Git tag:

- Tag: `recovery/local-assets-2026-09-11`
- Commit: `8fa12e5efc44a1dd8652d2af8a5f951cc5f03aa8`
- Contents: the working React/Python app, pagination, TTL caching, loading
  improvements, folder reorganization, and all 4,122 images in their original
  active `assets/` paths.

The CDN change is a separate commit tagged `migration/riot-cdn-2026-09-11`.
Both tags are local. No commits or tags were pushed to a remote.

## Undo just the CDN migration

Start with a clean working tree (`git status --short`). Commit or stash any new
work first. Then:

```powershell
git revert migration/riot-cdn-2026-09-11
npm ci
npm run build
npm run check:build
```

This creates a new undo commit, restores local image paths and the previous
build configuration, and preserves Git history. If later commits touch the same
files, resolve any revert conflicts before rebuilding.

## Return to the exact checkpoint

To put the complete checkpoint on its own branch, start with a clean working
tree and run:

```powershell
git switch -c restore-local-assets recovery/local-assets-2026-09-11
npm ci
npm run build
npm run check:build
```

Use a different new branch name if `restore-local-assets` already exists. Your
CDN migration and any subsequent commits remain on the original branch. Restart
the frontend and backend after recovery:

```powershell
# Terminal 1
npm run backend
# Terminal 2
npm run dev
```

Do not use `git clean -fdx`: it would remove ignored local settings and data.
Git deliberately excludes `config.env`, the SQLite runtime database, generated
builds, dependency folders, and logs. Those existing files were left in place;
the Git checkpoint covers source and artwork, not credentials or runtime state.
Keep separate private backups if those local files also need disaster recovery.

## Verification and storage

The Git object integrity check (`git fsck --full --no-dangling`) passed. The tag
contains all original active images. All 4,111 images moved to `archive/assets/`
were checked with SHA-256 before and after their move; the chronological record
is `archive/move-manifest.json`.

The archive preserves the earlier no-deletion requirement. It is excluded from
the production build but remains on disk, alongside any older generated-build
archives. Git also retains the original image blobs for restoration. This
migration primarily reduces active asset size and deployment output; preserving
archives and history does not eliminate their storage use.

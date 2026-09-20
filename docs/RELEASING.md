# Releasing

This repository is distributed via a HACS **custom repository**, with
`hacs.json`'s `hide_default_branch: true`. That setting means HACS only ever
offers users **tagged releases** — never the tip of `main` — so a change
isn't available to installs until it's tagged and released. There is no
separate "publish to HACS store" step: tagging a GitHub release *is* the
publish step.

## Steps

1. **Bump the version.** Edit `custom_components/geodrops/manifest.json` and
   set `"version"` to the new version (semver, no leading `v`, e.g. `0.2.0`).
   This must match the git tag you create below (the tag is `v0.2.0`, the
   manifest version is `0.2.0`).

2. **Write the release notes by hand.** HACS renders the GitHub release
   **body** as the changelog entry shown to users before they update — do
   **not** run `gh release create` with `--generate-notes` or leave the body
   empty. Write a short, human-readable summary of what changed and why it
   matters to someone deciding whether to update, not a raw commit log.

3. **Mirror the same notes into `CHANGELOG.md`**, as a new `## X.Y.Z`
   section above the previous entries. The changelog in the repo and the
   release notes on GitHub should say the same thing — write it once, paste
   it twice.

4. **Commit the version bump and changelog** on a normal branch, get it
   merged to `main` the usual way (this repo does not release from
   unmerged branches).

5. **Tag and release from `main`**, with hand-written notes passed inline:

   ```bash
   git checkout main
   git pull
   gh release create v0.2.0 --target main --title "v0.2.0" --notes "$(cat <<'EOF'
   - Short bullet of what changed.
   - Another bullet if needed.
   EOF
   )"
   ```

   Always pass `--target main` explicitly — don't rely on the default
   branch resolving correctly. Never pass `--generate-notes`: it produces a
   commit-log dump instead of the curated notes HACS shows users, and it
   defeats step 2 above.

6. **Verify in HACS.** After the release publishes, HACS should offer the
   new version as an update for existing installs (and as the version
   installed by new custom-repository installs) within its normal refresh
   window. Because `hide_default_branch: true` is set, confirm you released
   from a tag and not just pushed to `main` — a push alone will not show up
   in HACS.

## Notes

- Version numbers are semver (`MAJOR.MINOR.PATCH`). Bump `PATCH` for
  fixes, `MINOR` for backwards-compatible features (e.g. a new sensor),
  `MAJOR` for anything that breaks existing config entries or entity IDs.
- The manifest `version` and the git tag must agree, or HACS will show a
  confusing version mismatch to users comparing the release notes to what
  they see installed.

# `manifests/artifacts/` — stored-evidence manifests

One file per stored run: `<bench>-<run-id>.manifest.json`, written by
`python3 sim/run_corners.py <bench> --record --store` (issue #717). Each entry
names one object in the fleet artifact store by its sha256, with `size`,
`kind` (`evidence`), `producer` (`tool`, `version`, `loom.repo`, `commit`),
`uri` (always `artifact:<key>`) and `name`, the path the bytes would have had
under `sim/`. The format is klayout-tools' `docs/cli/artifact.md`.

Evidence bytes are private; these manifests are public. The run's Markdown
record under `sim/<bench>/records/` carries a "Stored evidence" table (name,
size, sha256 per object).

Manifests are append-only (`sim/check_append_only.py`): never edit or delete
one. `npm run check:artifact-manifests` validates the schema, accepts only
`artifact:` URIs, and fails if a stored object's bytes are also committed.
It never contacts the broker, so it does not hash-verify; run
`klt artifact verify <manifest>` (or
`python3 sim/check_artifact_manifests.py verify <manifest>`) from a fleet
worker with `$KLT_ARTIFACT_BROKER` set.

No file here names a storage bucket or cloud account, and the broker URL is
never written to the repo.

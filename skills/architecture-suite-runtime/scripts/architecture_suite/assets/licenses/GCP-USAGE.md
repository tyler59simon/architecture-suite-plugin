# Google Cloud icons (optional, not redistributed)

Architecture Suite does not ship Google Cloud icon files. Google's published guidance allows the
icons to be used in architecture diagrams, but we could not confirm terms that permit bundling them
in a redistributed tool (reviewed 2026-11-03). Source page: https://cloud.google.com/icons

What ships instead:

- `gcp-catalog.json`: service names, aliases and the expected file name of each icon.
- `manifest-gcp.json`: the SHA-256 of each icon file, so only unmodified official icons are accepted.

To use icons, download both official sets from https://cloud.google.com/icons yourself and run:

    architecture-suite install-gcp-icons --modern <extracted modern folder> --legacy-zip <legacy zip> --confirm-write

They are installed into `~/.architecture-suite/gcp-icons` (or the folder named by
`ARCHITECTURE_SUITE_GCP_ICONS`). Without them, Google Cloud elements render without icons and
everything else works. Google Cloud product names and icons are trademarks of Google LLC.

# Public macOS application release

## What is verified in 0.1.3

- The standalone Apple Silicon application launches from its bundled Python runtime.
- A frozen-app self-test runs Rest, MMN, VFT, N-back, and Emotion in software-only DEMO mode.
- The self-test writes five trial-level behavioral CSV files, trigger logs, session metadata, and an HTML report.
- The normal app stores outputs outside the read-only application bundle under `~/Library/Application Support/BPlus Research Toolkit/data/`.

These checks establish packaging and software workflow integrity. They do not establish EEG/fNIRS trigger timing, hardware compatibility, stimulus validity, diagnostic validity, or clinical safety.

## Build

Install the acquisition environment plus PyInstaller, then run:

```bash
BPLUS_BUILD_PYTHON=/path/to/python bash scripts/build_macos_app.sh
```

The build currently targets Apple Silicon (`arm64`). An Intel or universal package must be built and tested separately.

## Signing and notarization gate

The public preview is ad-hoc signed. A warning-free public installer requires all of the following:

1. An active Apple Developer Program account.
2. A valid Developer ID Application certificate in the build keychain.
3. Hardened-runtime signing of the application and its nested binaries.
4. Apple notarization and stapling.
5. Gatekeeper verification on a clean external Mac.

Do not label a build “notarized” until Apple returns an accepted notarization result and the ticket is stapled and verified.

## Laboratory acceptance gate

Before participant acquisition, complete the site-specific acceptance checklist in `docs/12_DEPLOYMENT_ACCEPTANCE.md`, including physical EEG/fNIRS event-marker tests, clock alignment, stimulus-display checks, audio calibration, and an approved ethics protocol.

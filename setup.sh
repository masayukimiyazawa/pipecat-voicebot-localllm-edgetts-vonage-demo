#!/usr/bin/env bash
set -euo pipefail

# TTS: pyopenjtalk has a bundled HTS voice — nothing to download.
echo "All voice models are bundled with pyopenjtalk-plus. Skipping download."
echo "Run 'pip install -e .' to install dependencies."

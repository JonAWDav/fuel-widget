---
name: install-fuel-widget
description: Download and set up the public Fuel AI usage widget on Windows or macOS for a user who asks to install, update, or try Fuel from GitHub.
---

# Install Fuel

Fuel is a Windows and macOS desktop overlay for AI usage and balance meters. Its public source is [JonAWDav/fuel-widget](https://github.com/JonAWDav/fuel-widget). The installers in this skill download that repo; they do not bundle a copy of the app.

When the user asks to install Fuel:

1. Detect the local OS. Fuel supports Windows 10/11 x64 and macOS on Apple Silicon or Intel. Ask for a folder the user wants to keep. Check Python 3.11+ and Node.js. Read the current [repo README](https://github.com/JonAWDav/fuel-widget#readme) for changed requirements before running setup. If the repo is unavailable, stop rather than substituting another source.
2. On Windows, use `scripts/install-fuel.ps1 -Destination '<chosen folder>'`. On macOS, use `bash scripts/install-fuel.sh '<chosen folder>'`. Each helper downloads the public GitHub main branch archive, refuses to replace an existing folder, checks for expected setup files, and runs the matching repo setup script. For a copy only, add `-DownloadOnly` on Windows or `--download-only` on macOS. For manual startup, add `-NoStartup` or `--no-startup` respectively.
3. Check the downloaded folder, setup output and running Fuel widget. For automatic startup, inspect the `AI Fuel Widget` scheduled task on Windows or `com.fuelwidget.app` launch agent on macOS and the app's `state/health.json`. Tell the user whether startup and each requested provider actually connected. Do not call a detected app a working usage meter unless it returns usage.
4. If Codex or Claude is disconnected, ask the user to sign into their own Codex CLI or Claude Code installation. Fuel reads those local accounts. Optional provider keys can come from the user's own existing environment; never ask them to paste keys into chat or place keys in the skill, repo, or logs.

Fuel makes read-only usage requests and calculates forecasts locally. It does not call AI models. It does use Python packages and network access during installation. Do not claim that a Claude or Codex skill can run local scripts in a plain web chat without computer access. In that case, provide the manual steps for the user's OS from the README.

For an existing installation, inspect it and the current README before proposing an update. Do not overwrite the folder or replace its settings or history. Do not automatically re-enable a deliberately stopped widget.

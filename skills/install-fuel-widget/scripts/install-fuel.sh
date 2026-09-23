#!/bin/sh
set -eu

if [ "$(uname -s)" != Darwin ]; then
    echo 'This installer supports macOS only.' >&2
    exit 1
fi
if [ "$#" -lt 1 ]; then
    echo 'Usage: install-fuel.sh DESTINATION [--download-only] [--no-startup]' >&2
    exit 1
fi

destination=$1
shift
download_only=false
no_startup=false
for option in "$@"; do
    case "$option" in
        --download-only) download_only=true ;;
        --no-startup) no_startup=true ;;
        *) echo "Unknown option: $option" >&2; exit 1 ;;
    esac
done

parent=$(dirname -- "$destination")
if [ ! -d "$parent" ]; then
    echo "Parent folder does not exist: $parent" >&2
    exit 1
fi
parent=$(CDPATH= cd -- "$parent" && pwd)
destination="$parent/$(basename -- "$destination")"
if [ -e "$destination" ]; then
    echo "Destination already exists: $destination. Choose a new folder." >&2
    exit 1
fi

if [ "$download_only" = false ]; then
    if ! command -v node >/dev/null 2>&1; then
        echo 'Install Node.js, then open a new Terminal window.' >&2
        exit 1
    fi
    python=''
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' >/dev/null 2>&1; then
            python="$candidate"
            break
        fi
    done
    if [ -z "$python" ]; then
        echo 'Install Python 3.11 or later, then open a new Terminal window.' >&2
        exit 1
    fi
fi

stage=$(mktemp -d "$parent/.fuel-download.XXXXXXXX")
archive="$stage/fuel-widget.zip"
curl --fail --location --silent --show-error \
    'https://github.com/JonAWDav/fuel-widget/archive/refs/heads/main.zip' \
    --output "$archive"
unzip -q "$archive" -d "$stage"
extracted="$stage/fuel-widget-main"
for required in README.md setup.sh install-macos.sh requirements.txt start-macos.sh; do
    if [ ! -f "$extracted/$required" ]; then
        echo "Downloaded archive is missing $required. Nothing was installed." >&2
        exit 1
    fi
done
mv "$extracted" "$destination"
rm "$archive"
rmdir "$stage"
echo "Downloaded Fuel to $destination"

if [ "$download_only" = true ]; then
    echo 'Download complete. Setup and automatic startup were not run.'
elif [ "$no_startup" = true ]; then
    bash "$destination/setup.sh" --no-startup
else
    bash "$destination/setup.sh"
fi

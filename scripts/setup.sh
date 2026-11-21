#!/usr/bin/env bash
# Desktop setup and paired launcher. Compatible with the Bash shipped on macOS.
set -eu
cd "$(dirname "$0")/.."
die() { echo "Setup: $*" >&2; exit 1; }
usage() { echo 'Usage: ./scripts/setup.sh [--check | --smoke-test | --start /path/to/config.toml]'; }
mode=${1:-setup}
case "$mode" in
    --help|-h) usage; exit 0 ;;
    --check|--smoke-test) [ "$#" = 1 ] || { usage; exit 2; } ;;
    --start) [ "$#" = 2 ] || { usage; exit 2; } ;;
    setup) [ "$#" = 0 ] || { usage; exit 2; } ;;
    *) usage; exit 2 ;;
esac

os=$(uname -s)
arch=$(uname -m)
distro=unknown
codename=unknown
model=''
tier='untested'
case "$os" in
    Linux)
        if [ -r /etc/os-release ]; then
            . /etc/os-release
            distro=${ID:-unknown}
            codename=${VERSION_CODENAME:-unknown}
        fi
        for file in /proc/device-tree/model /sys/firmware/devicetree/base/model; do
            if [ -r "$file" ]; then model=$(tr -d '\000' < "$file"); break; fi
        done
        bits=$(getconf LONG_BIT) || die 'Could not identify userspace bitness.'
        echo "Host: ${PRETTY_NAME:-Linux} ($distro/$codename), $arch, $bits-bit userspace; ${model:-PC or unknown board}"
        if [[ "$model" == *"Raspberry Pi"* ]]; then
            case "$model" in
                *"Zero 2"*) ;; # Different hardware from the original Zero / Zero W.
                *"Pi Zero"*) die 'The original Pi Zero and Zero W cannot run PiConsole.' ;;
            esac
            case "$distro:$codename:$bits" in
                debian:buster:*|raspbian:buster:*) die 'Use Raspberry Pi OS Bookworm or 64-bit Trixie. Buster is incompatible.' ;;
                debian:trixie:32|raspbian:trixie:32) die '32-bit Trixie is incompatible. Use 64-bit Trixie or Bookworm.' ;;
                debian:bookworm:*|raspbian:bookworm:*|debian:trixie:64|raspbian:trixie:64)
                    case "$model" in
                        *"Pi 3 Model B"*|*"Pi 4 Model B"*|*"Pi 5 Model B"*) tier='target' ;;
                    esac ;;
            esac
        elif [ "$distro" = ubuntu ] && [[ "${VERSION_ID:-}" =~ ^[0-9]+\.[0-9]+$ ]]; then
            if [[ "${VERSION_ID%%.*}" -gt 22 || "$VERSION_ID" = 22.04 || "$VERSION_ID" = 22.10 ]]; then tier='target'; fi
        fi ;;
    Darwin)
        echo "Host: macOS $(sw_vers -productVersion) ($arch)"
        case "$arch" in arm64|x86_64) tier='target' ;; esac ;;
    MINGW*|MSYS*|CYGWIN*) die 'Open PowerShell in the checkout and run .\scripts\setup-windows.cmd' ;;
    *) die "Unsupported host $os ($arch). Use macOS, Linux, Raspberry Pi OS Desktop or native Windows." ;;
esac

if [ "$tier" = untested ]; then
    echo 'Recognized host outside the documented hardware/OS targets. Compatibility is unverified.' >&2
    if [ "$mode" = setup ] || [ "$mode" = --smoke-test ]; then
        read -r -p 'Try setup on this host anyway? [y/N] ' reply || die 'Confirmation required.'
        case "$reply" in y|Y|yes|Yes) ;; *) die 'Cancelled.' ;; esac
    fi
fi
[ "$mode" = --check ] || [ "$(id -u)" != 0 ] || die 'Run setup as the account that will run the console.'
[ -f home_telemetry/setup_wizard.py ] && [ -f home_telemetry/config_setup.py ] || die 'Extract the full fork including the setup wizard.'
[ -w . ] || die 'The checkout must be writable by the console user.'

apt_offer() {
    local pkg=$1 reply
    echo "Suggested command: sudo apt-get install $pkg" >&2
    [ "$mode" != --check ] && [ "$mode" != --start ] || return 1
    command -v apt-get >/dev/null && command -v sudo >/dev/null || return 1
    read -r -p 'Run this command now? [y/N] ' reply || return 1
    case "$reply" in y|Y|yes|Yes) sudo apt-get install "$pkg" ;; *) return 1 ;; esac
}

valid='import sys; sys.exit(sys.implementation.name != "cpython" or sys.version_info < (3,11))'
find_python() {
    local candidate
    local candidates=(python3.12 python3.11 python3)
    if [ -n "${PYTHON:-}" ]; then candidates=("$PYTHON"); fi
    for candidate in "${candidates[@]}"; do
        if command -v "$candidate" >/dev/null && "$candidate" -B -c "$valid"; then
            interpreter=$candidate
            return 0
        fi
    done
    return 1
}
if [ -e .venv ] || [ -L .venv ]; then
    interpreter=.venv/bin/python
    [ -x "$interpreter" ] && "$interpreter" -B -c "$valid" &&
        "$interpreter" -B -c 'import sys; sys.exit(sys.prefix == sys.base_prefix)' ||
        die 'Incomplete, foreign or incompatible .venv. Rename it and rerun setup.'
else
    [ "$mode" != --start ] || die 'Run setup first.'
    if ! find_python; then
        if [ -z "${PYTHON:-}" ] && [[ "$distro" =~ ^(debian|raspbian|ubuntu)$ ]] &&
            [[ "$codename" =~ ^(bookworm|trixie|noble)$ ]]; then
            apt_offer python3 && find_python || die 'Install CPython 3.11+ and rerun setup.'
        else
            die 'Install CPython 3.11+ with venv support. Set PYTHON to its executable if necessary.'
        fi
    fi
    if ! "$interpreter" -B -c 'import venv, ensurepip; ensurepip.version()' >/dev/null 2>&1; then
        case "$distro" in
            debian|raspbian|ubuntu)
                version=$("$interpreter" -B -c 'import sys; print("%d.%d" % sys.version_info[:2])')
                apt_offer "python${version}-venv" || die 'The chosen Python needs matching venv/ensurepip support.' ;;
        esac
        "$interpreter" -B -c 'import venv, ensurepip; ensurepip.version()' || die 'Install venv support for the selected Python.'
    fi
fi
"$interpreter" -B -c 'import sys, ssl, sqlite3; print("Python:", sys.executable, sys.version.split()[0], "| SQLite:", sqlite3.sqlite_version, "| TLS:", ssl.OPENSSL_VERSION)' ||
    die 'The chosen Python must include working SSL and SQLite modules.'
if [ "$mode" = --check ]; then
    if [ -x .venv/bin/python ]; then
        .venv/bin/python -B -m pip --version || die 'Existing venv is missing pip. Rerun setup to attempt ensurepip.'
    fi
    echo 'Host preflight passed. Interactive setup verifies packages, graphics and the selected sensor.'
    exit 0
fi
if [ ! -x .venv/bin/python ]; then
    "$interpreter" -m venv .venv || die 'venv creation failed. Check disk space and ensurepip, rename any incomplete .venv and retry.'
fi
.venv/bin/python -m pip --version >/dev/null || .venv/bin/python -m ensurepip
exec .venv/bin/python -m home_telemetry.setup_wizard "$@"

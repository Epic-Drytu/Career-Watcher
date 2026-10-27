#!/bin/sh
set -eu

cd "$(dirname "$0")"

USE_SUDO=0

ask_to_install() {
    prompt=$1
    printf '%s [y/N] ' "$prompt"
    if [ ! -t 0 ]; then
        printf '\nThis installer needs an interactive terminal.\n' >&2
        return 1
    fi
    IFS= read -r answer || return 1
    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

docker_command() {
    if [ "$USE_SUDO" -eq 1 ]; then
        sudo docker "$@"
    else
        docker "$@"
    fi
}

wait_for_docker() {
    attempt=0
    while [ "$attempt" -lt 90 ]; do
        if docker info >/dev/null 2>&1; then
            return 0
        fi
        if [ "$USE_SUDO" -eq 1 ] && sudo docker info >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 2
    done
    return 1
}

OS=$(uname -s)

if ! command -v docker >/dev/null 2>&1; then
    case "$OS" in
        Darwin)
            if ! command -v brew >/dev/null 2>&1; then
                cat >&2 <<'EOF'
Docker is not installed, and Homebrew was not found.
Install Homebrew from https://brew.sh, then rerun ./setup-and-run.sh.
Alternatively, install Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/.
EOF
                exit 1
            fi
            printf '%s\n' 'Docker Desktop will be downloaded and installed with Homebrew.'
            printf '%s\n' 'After installation, Docker Desktop may ask you to accept its terms in the app.'
            if ! ask_to_install 'Install Docker Desktop now?'; then
                printf '%s\n' 'Docker installation cancelled.'
                exit 1
            fi
            brew install --cask docker-desktop
            ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                cat >&2 <<'EOF'
This looks like WSL. Install Docker Desktop for Windows, enable its WSL integration,
then rerun this script inside your WSL terminal:
https://docs.docker.com/desktop/features/wsl/
EOF
                exit 1
            fi
            if ! command -v curl >/dev/null 2>&1; then
                printf '%s\n' 'curl is required to download the official Docker installer.' >&2
                exit 1
            fi
            installer=$(mktemp "${TMPDIR:-/tmp}/career-watcher-docker-install.XXXXXX")
            trap 'rm -f "$installer"' 0
            printf '%s\n' 'Downloading Docker’s official Linux installation script.'
            curl --fail --silent --show-error --location https://get.docker.com --output "$installer"
            printf '\nDownloaded to: %s\n' "$installer"
            printf '%s\n' 'Docker documents this convenience installer for development environments; it requires sudo.'
            printf '%s\n' 'Review the downloaded script before approving installation.'
            printf 'Type install to run it with sudo: '
            if [ ! -t 0 ]; then
                printf '\nThis installer needs an interactive terminal.\n' >&2
                exit 1
            fi
            IFS= read -r answer || exit 1
            if [ "$answer" != install ]; then
                printf '%s\n' 'Docker installation cancelled.'
                exit 1
            fi
            sudo sh "$installer"
            USE_SUDO=1
            ;;
        *)
            printf 'Automatic Docker installation is not configured for %s. Install Docker manually, then rerun this script.\n' "$OS" >&2
            exit 1
            ;;
    esac
fi

if [ "$OS" = Darwin ] && ! command -v docker >/dev/null 2>&1; then
    for docker_bin_dir in "$HOME/.docker/bin" /usr/local/bin /opt/homebrew/bin \
        /Applications/Docker.app/Contents/Resources/bin; do
        if [ -x "$docker_bin_dir/docker" ]; then
            PATH="$docker_bin_dir:$PATH"
            export PATH
            break
        fi
    done
fi

if ! command -v docker >/dev/null 2>&1; then
    printf '%s\n' 'Docker CLI is still unavailable. Restart your terminal after installation, then rerun this script.' >&2
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    if [ "$OS" = Darwin ]; then
        printf '%s\n' 'Starting Docker Desktop. Complete any first-run setup or terms prompt in the app.'
        open -a Docker || {
            printf '%s\n' 'Could not open Docker Desktop. Start it from Applications, then rerun this script.' >&2
            exit 1
        }
        if ! wait_for_docker; then
            printf '%s\n' 'Docker did not become ready. Finish Docker Desktop setup and rerun this script.' >&2
            exit 1
        fi
    elif [ "$OS" = Linux ]; then
        if docker info >/dev/null 2>&1; then
            USE_SUDO=0
        elif sudo docker info >/dev/null 2>&1; then
            USE_SUDO=1
        else
            if command -v systemctl >/dev/null 2>&1; then
                sudo systemctl start docker
            fi
            USE_SUDO=1
            if ! wait_for_docker; then
                printf '%s\n' 'Docker Engine is not running or is inaccessible. Check your Docker installation, then rerun this script.' >&2
                exit 1
            fi
        fi
    fi
fi

if [ ! -t 0 ]; then
    printf '%s\n' 'Run this script from an interactive terminal so Docker can ask before launching the app.' >&2
    exit 1
fi

printf '\n%s\n' 'Building Career Watcher image...'
docker_command build --tag career-watcher:local .
docker_command volume create career-watcher-data >/dev/null
printf '\n%s\n' 'Starting Career Watcher. Its own launch prompt will appear next.'
docker_command run --rm -it \
    --publish 127.0.0.1:8765:8765 \
    --volume career-watcher-data:/data \
    career-watcher:local

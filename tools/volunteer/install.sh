#!/bin/sh
# PlanWAT volunteer crawler: the installer, and afterwards the `planwat-crawler` command (docs/WOLONTARIUSZE.md).
#
#   curl -fsSLO https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/install.sh
#   less install.sh          # read it first: it installs software and asks for sudo
#   sh install.sh
#
# Linux (Debian, Ubuntu, Raspberry Pi OS 64-bit, Mint, Fedora, RHEL/CentOS/Rocky/Alma, Arch, openSUSE; also WSL2)
# and macOS (Homebrew + Colima, no Docker Desktop needed). On amd64 and arm64. It is idempotent: run it again to
# repair an installation. What it does, after showing the plan and asking once:
#   1. installs what is missing: Docker Engine with Compose (Docker's own signed repositories, or the distro's on
#      Arch/openSUSE, Colima on macOS) and the GitHub CLI (only to verify image provenance);
#   2. asks for your GitHub login and a fine-grained token limited to your fork (links prefilled);
#   3. pulls the crawler and egress images of the latest release, checks their build provenance with
#      `gh attestation verify` (built by crawler-image.yml in kilerdevs/PlanWAT, nothing else) and pins them by
#      digest, so nothing unverified ever runs, the setup wizard included;
#   4. runs the setup wizard inside the verified image (fork, token, faculties, registry, auto-updates);
#   5. starts the crawler, and (unless you opt out) schedules a daily verified update with rollback.
# It never adds you to the docker group (that is root by another name); it uses sudo where it needs to.
#
# Afterwards this script is ~/.local/bin/planwat-crawler:
#   status | logs | doctor | setup | update | autoupdate on|off | start | stop | restart | uninstall | version
#
# For tests and development: --check (plan only), --yes, --no-start, --no-verify, --version X.Y.Z, and
# PLANWAT_INSTALL_SOURCE=<checkout> (install the compose file and this script from a local checkout),
# PLANWAT_CRAWLER_IMAGE / PLANWAT_EGRESS_IMAGE (use these images; with --no-verify), PLANWAT_LOGIN and
# PLANWAT_FORK_TOKEN (no prompts), PLANWAT_SETUP_ARGS (extra wizard flags).
set -eu

REPO=kilerdevs/PlanWAT
SIGNER="$REPO/.github/workflows/crawler-image.yml"
IMAGES='planwat-crawler planwat-crawler-egress'
GH_MIN=2.49.0
APP="${PLANWAT_HOME:-$HOME/.local/share/planwat-crawler}"
BIN="${PLANWAT_BIN:-$HOME/.local/bin}"
SOURCE="${PLANWAT_INSTALL_SOURCE:-}"
ENV_FILE="$APP/.env"
UNIT=planwat-crawler-update
AGENT=pl.planwat.crawler-update

say() { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
warn() { printf 'Uwaga: %s\n' "$*" >&2; }
die() { printf 'Błąd: %s\n' "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- small tools ----------------------------------------------------------------------------------------------

ver_ge() {  # ver_ge A B: A >= B (dotted numbers)
  awk -v a="$1" -v b="$2" 'BEGIN { n = split(a, x, "."); m = split(b, y, ".");
    for (i = 1; i <= (n > m ? n : m); i++) { if (x[i] + 0 > y[i] + 0) exit 0; if (x[i] + 0 < y[i] + 0) exit 1 }
    exit 0 }'
}

env_get() {  # the value of KEY in .env ('' when absent)
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^$1=//p" "$ENV_FILE" | tail -n 1
}

env_set() {  # set KEY=VALUE in .env, keeping every other line; mode 0600
  mkdir -p "$APP"
  umask 077
  touch "$ENV_FILE"
  awk -v k="$1" -v v="$2" 'BEGIN { done = 0 }
    $0 ~ "^#? *" k "=" { if (!done) { print k "=" v; done = 1 } ; next }
    { print }
    END { if (!done) print k "=" v }' "$ENV_FILE" > "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
}

fetch() {  # fetch URL FILE
  curl -fsSL --proto '=https' --tlsv1.2 --retry 3 --max-time 120 -o "$2" "$1"
}

ask() {  # ask VAR "question" [default]
  if [ -n "${3:-}" ]; then printf '%s [%s]: ' "$2" "$3"; else printf '%s: ' "$2"; fi
  read -r _answer || _answer=''
  [ -n "$_answer" ] || _answer="${3:-}"
  eval "$1=\$_answer"
}

ask_secret() {  # ask_secret VAR "question"
  printf '%s: ' "$2"
  stty -echo 2>/dev/null || true
  read -r _answer || _answer=''
  stty echo 2>/dev/null || true
  printf '\n'
  eval "$1=\$_answer"
}

confirm() {  # confirm "question" (default yes; --yes answers it)
  [ "$YES" = 1 ] && return 0
  printf '%s [T/n]: ' "$1"
  read -r _answer || _answer=''
  case "$_answer" in ''|t|T|tak|y|Y|yes) return 0 ;; *) return 1 ;; esac
}

# --- the machine ----------------------------------------------------------------------------------------------

os_field() { sed -n "s/^$1=//p" /etc/os-release 2>/dev/null | tr -d '"' | head -n 1; }

detect() {
  OS=$(uname -s)
  case "$(uname -m)" in
    x86_64|amd64) ARCH=amd64 ;;
    aarch64|arm64) ARCH=arm64 ;;
    *) die "procesor $(uname -m) nie jest obsługiwany: obrazy crawlera są dla amd64 i arm64 (Raspberry Pi: system 64-bitowy)" ;;
  esac
  FAMILY=unknown
  WSL=0
  if [ "$OS" = Darwin ]; then
    FAMILY=macos
  elif [ "$OS" = Linux ]; then
    id=$(os_field ID); like=$(os_field ID_LIKE)
    case " $id $like " in
      *" ubuntu "*) FAMILY=ubuntu; CODENAME=$(os_field UBUNTU_CODENAME); [ -n "$CODENAME" ] || CODENAME=$(os_field VERSION_CODENAME) ;;
      *" debian "*|*" raspbian "*) FAMILY=debian; CODENAME=$(os_field VERSION_CODENAME) ;;
      *" fedora "*) FAMILY=fedora ;;
      *" rhel "*|*" centos "*|*" rocky "*|*" almalinux "*) FAMILY=rhel; [ "$id" = rhel ] && RHEL_REPO=rhel || RHEL_REPO=centos ;;
      *" arch "*|*" manjaro "*|*" endeavouros "*) FAMILY=arch ;;
      *" opensuse"*|*" suse "*|*" sles "*) FAMILY=suse ;;
    esac
    case " $id $like " in *" fedora "*) FAMILY=fedora ;; esac
    if grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; then WSL=1; fi
  else
    die "system $OS nie jest obsługiwany przez ten skrypt (Windows: install.ps1)"
  fi
  if [ "$(id -u)" = 0 ]; then SUDO=''; elif have sudo; then SUDO=sudo; else SUDO=''; fi
}

docker_ok() { have docker && docker compose version >/dev/null 2>&1; }

gh_ok() {
  have gh || return 1
  v=$(gh --version 2>/dev/null | sed -n 's/^gh version \([0-9.]*\).*/\1/p' | head -n 1)
  [ -n "$v" ] && ver_ge "$v" "$GH_MIN"
}

pick_docker() {  # DOCKER: how to call docker here (never by joining the docker group)
  if docker info >/dev/null 2>&1; then DOCKER=docker
  elif [ -n "$SUDO" ] && $SUDO docker info >/dev/null 2>&1; then DOCKER="$SUDO docker"
  else DOCKER=''
  fi
}

compose() {
  # shellcheck disable=SC2086  # DOCKER is "docker" or "sudo docker"
  $DOCKER compose --project-name planwat-crawler --project-directory "$APP" -f "$APP/compose.yml" "$@"
}

# --- installing software --------------------------------------------------------------------------------------

need_root() {
  [ "$(id -u)" = 0 ] || [ -n "$SUDO" ] || die "potrzebuję uprawnień administratora (sudo), żeby zainstalować $1"
}

install_docker() {
  need_root Dockera
  case "$FAMILY" in
    debian|ubuntu)
      $SUDO apt-get update -q
      $SUDO apt-get install -y -q ca-certificates curl
      $SUDO install -m 0755 -d /etc/apt/keyrings
      $SUDO curl -fsSL "https://download.docker.com/linux/$FAMILY/gpg" -o /etc/apt/keyrings/docker.asc
      $SUDO chmod a+r /etc/apt/keyrings/docker.asc
      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' \
        "$(dpkg --print-architecture)" "$FAMILY" "$CODENAME" | $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null
      $SUDO apt-get update -q
      $SUDO apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin ;;
    fedora|rhel)
      if rpm -q podman-docker >/dev/null 2>&1; then
        die "pakiet podman-docker zajmuje polecenie docker; usuń go (sudo dnf remove podman-docker) i uruchom ponownie"
      fi
      repo=fedora; [ "$FAMILY" = rhel ] && repo=$RHEL_REPO
      $SUDO dnf -y -q install dnf-plugins-core
      if dnf --version 2>/dev/null | grep -q '^dnf5'; then
        $SUDO dnf config-manager addrepo --overwrite --from-repofile="https://download.docker.com/linux/$repo/docker-ce.repo"
      else
        $SUDO dnf config-manager --add-repo "https://download.docker.com/linux/$repo/docker-ce.repo"
      fi
      $SUDO dnf -y -q install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin ;;
    arch) $SUDO pacman -S --needed --noconfirm docker docker-compose ;;
    suse) $SUDO zypper -n install docker docker-compose ;;
    macos)
      brew install colima docker docker-compose
      mkdir -p "$HOME/.docker/cli-plugins"
      ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" "$HOME/.docker/cli-plugins/docker-compose" ;;
    *) die "nie umiem zainstalować Dockera na tym systemie; zainstaluj Docker Engine z Compose v2 i uruchom ponownie" ;;
  esac
}

start_docker() {
  if [ "$FAMILY" = macos ]; then
    brew services start colima >/dev/null 2>&1 || colima start
  elif have systemctl && [ -d /run/systemd/system ]; then
    $SUDO systemctl enable --now docker >/dev/null 2>&1 || $SUDO systemctl start docker
  elif [ "$WSL" = 1 ]; then
    die "WSL bez systemd: dopisz do /etc/wsl.conf sekcję [boot] z systemd=true, wykonaj w Windows 'wsl --shutdown' i uruchom ponownie"
  fi
  tries=0
  pick_docker
  while [ -z "$DOCKER" ] && [ $tries -lt 30 ]; do sleep 2; tries=$((tries + 1)); pick_docker; done
  [ -n "$DOCKER" ] || die "Docker nie odpowiada (docker info); sprawdź: sudo systemctl status docker"
}

install_gh() {
  case "$FAMILY" in
    debian|ubuntu)
      need_root 'GitHub CLI'
      $SUDO install -m 0755 -d /etc/apt/keyrings
      $SUDO curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
      $SUDO chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
      printf 'deb [arch=%s signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\n' \
        "$(dpkg --print-architecture)" | $SUDO tee /etc/apt/sources.list.d/github-cli.list >/dev/null
      $SUDO apt-get update -q && $SUDO apt-get install -y -q gh ;;
    fedora) need_root 'GitHub CLI'; $SUDO dnf -y -q install gh ;;
    rhel)
      need_root 'GitHub CLI'
      if dnf --version 2>/dev/null | grep -q '^dnf5'; then
        $SUDO dnf config-manager addrepo --overwrite --from-repofile=https://cli.github.com/packages/rpm/gh-cli.repo
      else
        $SUDO dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
      fi
      $SUDO dnf -y -q install gh ;;
    arch) need_root 'GitHub CLI'; $SUDO pacman -S --needed --noconfirm github-cli ;;
    suse) need_root 'GitHub CLI'; $SUDO zypper -n install gh ;;
    macos) brew install gh ;;
    *) die "zainstaluj GitHub CLI (https://cli.github.com) i uruchom ponownie" ;;
  esac
}

# --- releases, images, provenance -----------------------------------------------------------------------------

latest_version() {
  curl -fsSL --proto '=https' --max-time 30 "https://api.github.com/repos/$REPO/releases/latest" \
    | sed -n 's/.*"tag_name": *"v\{0,1\}\([0-9][0-9.]*\)".*/\1/p' | head -n 1
}

fetch_release_files() {  # fetch_release_files VERSION: compose.yml and this command, from that release
  mkdir -p "$APP" "$BIN"
  if [ -n "$SOURCE" ]; then
    cp "$SOURCE/tools/volunteer/compose.volunteer.yml" "$APP/compose.yml.new"
    cp "$SOURCE/tools/volunteer/install.sh" "$BIN/planwat-crawler.new"
  else
    raw="https://raw.githubusercontent.com/$REPO/v$1/tools/volunteer"
    fetch "$raw/compose.volunteer.yml" "$APP/compose.yml.new" || die "nie mogę pobrać compose.yml wydania $1"
    if ! fetch "$raw/install.sh" "$BIN/planwat-crawler.new"; then
      [ -f "$0" ] && cp "$0" "$BIN/planwat-crawler.new" || die "nie mogę pobrać polecenia planwat-crawler"
    fi
  fi
  chmod 755 "$BIN/planwat-crawler.new"
}

commit_release_files() {
  [ -f "$APP/compose.yml" ] && cp "$APP/compose.yml" "$APP/compose.yml.prev"
  mv "$APP/compose.yml.new" "$APP/compose.yml"
  mv "$BIN/planwat-crawler.new" "$BIN/planwat-crawler"
}

verify_images() {  # verify_images VERSION: pull, check provenance, set PIN_CRAWLER / PIN_EGRESS (digest refs)
  if [ "$VERIFY" = 0 ]; then
    PIN_CRAWLER="${PLANWAT_CRAWLER_IMAGE:-ghcr.io/kilerdevs/planwat-crawler:$1}"
    PIN_EGRESS="${PLANWAT_EGRESS_IMAGE:-ghcr.io/kilerdevs/planwat-crawler-egress:$1}"
    warn "pomijam weryfikację pochodzenia obrazów (--no-verify)"
    return 0
  fi
  token=$(env_get PLANWAT_FORK_TOKEN)
  [ -n "$token" ] || die "brak tokenu w $ENV_FILE (potrzebny do weryfikacji obrazów): planwat-crawler setup"
  for name in $IMAGES; do
    ref="ghcr.io/kilerdevs/$name:$1"
    say "  pobieram $ref"
    # shellcheck disable=SC2086
    $DOCKER pull -q "$ref" >/dev/null || die "nie mogę pobrać $ref"
    # shellcheck disable=SC2086
    pinned=$($DOCKER image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$ref" \
      | grep "^ghcr.io/kilerdevs/$name@sha256:" | head -n 1)
    [ -n "$pinned" ] || die "nie znam skrótu (digest) obrazu $ref"
    if ! GH_TOKEN="$token" GH_PROMPT_DISABLED=1 gh attestation verify "oci://$pinned" --repo "$REPO" \
        --signer-workflow "$SIGNER" >/dev/null 2>"$APP/verify.log"; then
      sed -n '1,5p' "$APP/verify.log" >&2
      die "obraz $pinned NIE przeszedł weryfikacji pochodzenia; nic nie zostało zmienione"
    fi
    say "  ✓ $name: zbudowany przez crawler-image.yml w $REPO ($pinned)"
    case "$name" in planwat-crawler) PIN_CRAWLER=$pinned ;; *) PIN_EGRESS=$pinned ;; esac
  done
}

pin_images() {  # remember the previous pins (for a rollback), then set the new ones
  env_set PLANWAT_PREVIOUS_CRAWLER_IMAGE "$(env_get PLANWAT_CRAWLER_IMAGE)"
  env_set PLANWAT_PREVIOUS_EGRESS_IMAGE "$(env_get PLANWAT_EGRESS_IMAGE)"
  env_set PLANWAT_CRAWLER_IMAGE "$PIN_CRAWLER"
  env_set PLANWAT_EGRESS_IMAGE "$PIN_EGRESS"
}

# --- identity (asked on the host: the token is needed to verify the images before anything runs) -------------

identity() {
  login="${PLANWAT_LOGIN:-$(env_get PLANWAT_LOGIN)}"
  token="${PLANWAT_FORK_TOKEN:-$(env_get PLANWAT_FORK_TOKEN)}"
  if [ -z "$login" ]; then
    [ -t 0 ] || die "brak PLANWAT_LOGIN (uruchom w terminalu albo ustaw zmienną)"
    while :; do
      ask login 'Twój login na GitHubie'
      printf '%s' "$login" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9-]{0,38}$' && break
      say '  To nie wygląda na login GitHub.'
    done
  fi
  env_set PLANWAT_LOGIN "$login"
  if [ -z "$token" ]; then
    [ -t 0 ] || die "brak PLANWAT_FORK_TOKEN (uruchom w terminalu albo ustaw zmienną)"
    say ''
    say 'Crawler pracuje na Twoim forku projektu i wypycha do niego paczki tokenem, który widzi tylko ten fork.'
    say "1. Jeśli nie masz jeszcze forka, utwórz go (Create fork): https://github.com/$REPO/fork"
    say '2. Utwórz token (formularz jest częściowo wypełniony):'
    say "   https://github.com/settings/personal-access-tokens/new?name=PlanWAT+crawler&target_name=$login&expires_in=90&contents=write"
    say "   Repository access: Only select repositories → $login/PlanWAT (Twój fork)."
    say '   Permissions → Repository permissions → Contents: Read and write. Nic więcej.'
    say '3. Wklej token (nie będzie widoczny).'
    while :; do
      ask_secret token 'Token'
      case "$token" in
        github_pat_*) break ;;
        ghp_*|gho_*) say '  To token klasyczny/OAuth (dostęp do wszystkich repozytoriów). Potrzebny fine-grained (github_pat_…).' ;;
        *) say '  To nie wygląda na token fine-grained (zaczyna się od github_pat_).' ;;
      esac
    done
  fi
  env_set PLANWAT_FORK_TOKEN "$token"
}

# --- scheduled updates ----------------------------------------------------------------------------------------

autoupdate_on() {
  env_set PLANWAT_AUTO_UPDATE 1
  if [ "$OS" = Darwin ]; then
    mkdir -p "$HOME/Library/LaunchAgents"
    plist="$HOME/Library/LaunchAgents/$AGENT.plist"
    cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$AGENT</string>
  <key>ProgramArguments</key><array><string>/bin/sh</string><string>$BIN/planwat-crawler</string><string>update</string><string>--auto</string></array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string><key>PLANWAT_HOME</key><string>$APP</string></dict>
  <key>StartCalendarInterval</key><dict><key>Hour</key><integer>4</integer><key>Minute</key><integer>$(awk 'BEGIN{srand(); print int(rand()*60)}')</integer></dict>
  <key>StandardOutPath</key><string>$APP/update.log</string><key>StandardErrorPath</key><string>$APP/update.log</string>
</dict></plist>
PLIST
    launchctl bootout "gui/$(id -u)/$AGENT" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$(id -u)" "$plist"
  elif have systemctl && [ -d /run/systemd/system ]; then
    need_root 'harmonogramu aktualizacji'
    user=root; [ "$DOCKER" = docker ] && user=$(id -un)
    printf '%s\n' '[Unit]' 'Description=PlanWAT volunteer crawler: verified update' 'Wants=network-online.target' \
      'After=network-online.target docker.service' '' '[Service]' 'Type=oneshot' "User=$user" \
      "Environment=PLANWAT_HOME=$APP" "Environment=HOME=$HOME" "ExecStart=/bin/sh $BIN/planwat-crawler update --auto" \
      | $SUDO tee "/etc/systemd/system/$UNIT.service" >/dev/null
    printf '%s\n' '[Unit]' 'Description=PlanWAT volunteer crawler: daily verified update' '' '[Timer]' \
      'OnCalendar=*-*-* 04:00:00' 'RandomizedDelaySec=3h' 'Persistent=true' '' '[Install]' 'WantedBy=timers.target' \
      | $SUDO tee "/etc/systemd/system/$UNIT.timer" >/dev/null
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable --now "$UNIT.timer" >/dev/null
  elif [ -d /etc/cron.d ]; then
    need_root 'harmonogramu aktualizacji'
    printf '%s %s * * * root PLANWAT_HOME=%s HOME=%s /bin/sh %s update --auto >> %s 2>&1\n' \
      "$(awk 'BEGIN{srand(); print int(rand()*60)}')" "$(awk 'BEGIN{srand(); print 3 + int(rand()*3)}')" \
      "$APP" "$HOME" "$BIN/planwat-crawler" "$APP/update.log" | $SUDO tee /etc/cron.d/$UNIT >/dev/null
  else
    warn "nie znalazłem systemd ani crona: aktualizuj ręcznie (planwat-crawler update)"
    return 0
  fi
  say '  ✓ automatyczne aktualizacje: raz dziennie, tylko zweryfikowane obrazy (planwat-crawler autoupdate off wyłącza)'
}

autoupdate_off() {
  env_set PLANWAT_AUTO_UPDATE 0
  if [ "$OS" = Darwin ]; then
    launchctl bootout "gui/$(id -u)/$AGENT" >/dev/null 2>&1 || true
    rm -f "$HOME/Library/LaunchAgents/$AGENT.plist"
  else
    if have systemctl && [ -f "/etc/systemd/system/$UNIT.timer" ]; then
      $SUDO systemctl disable --now "$UNIT.timer" >/dev/null 2>&1 || true
      $SUDO rm -f "/etc/systemd/system/$UNIT.timer" "/etc/systemd/system/$UNIT.service"
      $SUDO systemctl daemon-reload
    fi
    [ -f "/etc/cron.d/$UNIT" ] && $SUDO rm -f "/etc/cron.d/$UNIT"
  fi
  say '  automatyczne aktualizacje wyłączone; crawler zgłosi w logu, gdy pojawi się nowa wersja (planwat-crawler update)'
}

# --- commands -------------------------------------------------------------------------------------------------

cmd_install() {
  CHECK=0; START=1
  while [ $# -gt 0 ]; do
    case "$1" in
      --check) CHECK=1 ;;
      --yes|-y) YES=1 ;;
      --no-start) START=0 ;;
      --no-verify) VERIFY=0 ;;
      --version) shift; VERSION="${1:-}" ;;
      *) die "nieznana opcja: $1" ;;
    esac
    shift
  done
  detect
  plan=''
  docker_ok || plan="$plan
  - Docker Engine z Compose ($([ "$FAMILY" = macos ] && echo 'Homebrew: colima, docker, docker-compose' || echo "repozytorium Dockera dla $FAMILY"))"
  [ "$VERIFY" = 0 ] || gh_ok || plan="$plan
  - GitHub CLI >= $GH_MIN (tylko do weryfikacji pochodzenia obrazów)"
  [ "$FAMILY" = macos ] && ! have brew && die "potrzebny Homebrew: https://brew.sh (zainstaluj go i uruchom ten skrypt ponownie)"
  say "PlanWAT: instalacja crawlera wolontariusza"
  say "System: $OS/$ARCH ($FAMILY$([ "$WSL" = 1 ] && echo ', WSL'))"
  say "Katalog: $APP, polecenie: $BIN/planwat-crawler"
  if [ -n "$plan" ]; then say "Do zainstalowania:$plan"; else say 'Potrzebne programy już są.'; fi
  say "Potem: obrazy crawlera z weryfikacją pochodzenia, kreator konfiguracji, start i codzienne aktualizacje."
  if [ "$CHECK" = 1 ]; then return 0; fi
  confirm 'Kontynuować?' || die 'przerwano'
  if ! docker_ok; then step 'Docker'; install_docker; fi
  if [ "$VERIFY" = 1 ] && ! gh_ok; then step 'GitHub CLI'; install_gh; fi
  start_docker
  step 'Wydanie'
  [ -n "$VERSION" ] || VERSION=$(latest_version)
  [ -n "$VERSION" ] || die "nie mogę odczytać najnowszego wydania $REPO"
  say "  wersja $VERSION"
  fetch_release_files "$VERSION"
  commit_release_files
  step 'Konto i token'
  identity
  step 'Obrazy'
  verify_images "$VERSION"
  pin_images
  env_set PLANWAT_VERSION "$VERSION"
  step 'Konfiguracja'
  # The wizard runs in the verified image as you (so it can write .env here), with the token from .env.
  # shellcheck disable=SC2086  # PLANWAT_SETUP_ARGS is a list of flags
  compose run --rm --user "$(id -u):$(id -g)" -v "$APP:/config" crawler \
    setup --env /config/.env --keep-token --login "$(env_get PLANWAT_LOGIN)" ${PLANWAT_SETUP_ARGS:-} \
    || die "kreator przerwany; uruchom ponownie: planwat-crawler setup"
  step 'Diagnostyka'
  compose run --rm crawler doctor --no-probe || true
  if [ "$(env_get PLANWAT_AUTO_UPDATE)" = 0 ]; then autoupdate_off; else autoupdate_on; fi
  if [ "$START" = 1 ]; then
    step 'Start'
    compose up -d
    say ''
    say '✓ Crawler działa. Przydatne polecenia:'
  else
    say ''
    say '✓ Zainstalowano (bez startu: planwat-crawler start).'
  fi
  say '  planwat-crawler status     co robi teraz i co koordynator powiedział o ostatniej paczce'
  say '  planwat-crawler logs       dziennik na żywo'
  say '  planwat-crawler doctor     pełna diagnostyka z podpowiedziami'
  case ":$PATH:" in *":$BIN:"*) ;; *) say "  (dopisz $BIN do PATH albo wołaj $BIN/planwat-crawler)" ;; esac
}

cmd_update() {
  auto=0; force=0
  while [ $# -gt 0 ]; do
    case "$1" in
      --auto) auto=1 ;;
      --version) shift; VERSION="${1:-}"; force=1 ;;
      --no-verify) VERIFY=0 ;;
      *) die "nieznana opcja: $1" ;;
    esac
    shift
  done
  [ "$auto" = 1 ] && [ "$(env_get PLANWAT_AUTO_UPDATE)" = 0 ] && return 0
  [ "$auto" = 1 ] && say "== $(date -u '+%Y-%m-%d %H:%M:%S') UTC: automatyczna aktualizacja"
  installed=$(env_get PLANWAT_VERSION)
  [ -n "$VERSION" ] || VERSION=$(latest_version)
  [ -n "$VERSION" ] || die "nie mogę odczytać najnowszego wydania $REPO"
  if [ "$force" = 0 ] && [ -n "$installed" ] && ver_ge "$installed" "$VERSION"; then
    say "Masz najnowszą wersję ($installed)."
    return 0
  fi
  say "Aktualizacja ${installed:-?} → $VERSION"
  fetch_release_files "$VERSION"
  verify_images "$VERSION"
  pin_images
  commit_release_files
  compose up -d --remove-orphans
  say '  sprawdzam, czy nowa wersja działa…'
  sleep "${PLANWAT_UPDATE_SETTLE:-90}"
  running=$(compose ps --status running --services 2>/dev/null || true)
  case "$running" in
    *crawler*egress*|*egress*crawler*)
      env_set PLANWAT_VERSION "$VERSION"
      say "✓ zaktualizowano do $VERSION" ;;
    *)
      warn "nowa wersja nie wystartowała; wracam do poprzedniej"
      env_set PLANWAT_CRAWLER_IMAGE "$(env_get PLANWAT_PREVIOUS_CRAWLER_IMAGE)"
      env_set PLANWAT_EGRESS_IMAGE "$(env_get PLANWAT_PREVIOUS_EGRESS_IMAGE)"
      [ -f "$APP/compose.yml.prev" ] && cp "$APP/compose.yml.prev" "$APP/compose.yml"
      compose up -d --remove-orphans
      die "aktualizacja do $VERSION cofnięta (zostaje ${installed:-poprzednia})" ;;
  esac
}

cmd_uninstall() {
  confirm 'Usunąć crawler, jego dane i harmonogram aktualizacji?' || die 'przerwano'
  [ -f "$APP/compose.yml" ] && compose down -v --remove-orphans || true
  autoupdate_off >/dev/null 2>&1 || true
  rm -rf "$APP"
  rm -f "$BIN/planwat-crawler"
  say '✓ Usunięto. Dokończ na GitHubie:'
  say '  - usuń token: https://github.com/settings/personal-access-tokens'
  say '  - jeśli chcesz, usuń gałąź crawl ze swojego forka i napisz w swoim zgłoszeniu, że rezygnujesz'
}

running() { compose ps --status running --services 2>/dev/null | grep -qx crawler; }

in_crawler() {  # run an entrypoint command in the running crawler, or in a one-off container
  if running; then compose exec -T crawler /app/tools/volunteer/entrypoint.sh "$@"
  else compose run --rm crawler "$@"
  fi
}

main() {
  YES=0; VERIFY=1; VERSION=''
  cmd="${1:-}"
  case "$cmd" in
    ''|install) [ $# -gt 0 ] && shift; cmd_install "$@"; return ;;
    --*) cmd_install "$@"; return ;;
  esac
  shift
  detect
  [ -f "$APP/compose.yml" ] || die "crawler nie jest zainstalowany ($APP); uruchom install.sh"
  pick_docker
  [ -n "$DOCKER" ] || die "Docker nie odpowiada"
  case "$cmd" in
    status) in_crawler status ;;
    doctor) in_crawler doctor "$@" ;;
    logs) compose logs -f --tail "${1:-200}" crawler ;;
    setup)
      compose run --rm --user "$(id -u):$(id -g)" -v "$APP:/config" crawler setup --env /config/.env "$@"
      compose up -d ;;
    update) cmd_update "$@" ;;
    autoupdate)
      case "${1:-}" in
        on) autoupdate_on ;;
        off) autoupdate_off ;;
        *) say "automatyczne aktualizacje: $([ "$(env_get PLANWAT_AUTO_UPDATE)" = 0 ] && echo wyłączone || echo włączone)" ;;
      esac ;;
    start) compose up -d ;;
    stop) compose stop ;;
    restart) compose restart ;;
    uninstall) cmd_uninstall ;;
    version) say "planwat-crawler $(env_get PLANWAT_VERSION)" ;;
    help|-h) sed -n '2,30p' "$0" ;;
    *) die "nieznane polecenie: $cmd (status, logs, doctor, setup, update, autoupdate on|off, start, stop, restart, uninstall)" ;;
  esac
}

main "$@"

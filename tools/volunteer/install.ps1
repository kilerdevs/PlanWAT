# PlanWAT volunteer crawler for Windows: the installer, and afterwards the `planwat-crawler` command
# (docs/WOLONTARIUSZE.md). The same steps as install.sh, on Docker Desktop:
#
#   irm https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/install.ps1 -OutFile planwat-install.ps1
#   notepad planwat-install.ps1        # read it first
#   powershell -ExecutionPolicy Bypass -File .\planwat-install.ps1
#
#   1. installs what is missing with winget: Docker Desktop (it brings WSL2; a restart may be needed, then run
#      this again: it picks up where it stopped) and the GitHub CLI (only to verify image provenance);
#   2. asks for your GitHub login and a fine-grained token limited to your fork;
#   3. pulls the release images, checks their build provenance (gh attestation verify, built by crawler-image.yml
#      in kilerdevs/PlanWAT) and pins them by digest, so nothing unverified runs, the setup wizard included;
#   4. runs the setup wizard inside the verified image, starts the crawler, and (unless you opt out) schedules a
#      daily verified update with rollback (Task Scheduler).
#
# Afterwards: planwat-crawler status | logs [egress] | doctor | setup | update | autoupdate on|off | start | stop |
#             restart | uninstall [--yes] | version
# Channels (-Channel, remembered in .env, followed by updates): stable (default) installs the latest release, dev
# installs the dev branch's files and the :dev images crawler-image.yml publishes from it; both verified alike.
# Development: -Check (plan only), -Yes, -NoStart, -NoVerify, -Version X.Y.Z, $env:PLANWAT_INSTALL_SOURCE.
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string] $Command = 'install',
    [Parameter(Position = 1)] [string] $Argument = '',
    [switch] $Check,
    [switch] $Yes,
    [switch] $NoStart,
    [switch] $NoVerify,
    [switch] $Auto,
    [string] $Version = '',
    [string] $Channel = ''
)
$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { Write-Verbose 'console encoding unchanged' }

$Repo = 'kilerdevs/PlanWAT'
$Signer = "$Repo/.github/workflows/crawler-image.yml"
$Images = @('planwat-crawler', 'planwat-crawler-egress')
$GhMin = [version]'2.49.0'
$Root = Join-Path $env:LOCALAPPDATA 'PlanWAT'
$App = Join-Path $Root 'crawler'
$EnvFile = Join-Path $App '.env'
$CommandFile = Join-Path $Root 'planwat-crawler.ps1'
$Shim = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\planwat-crawler.cmd'
$TaskName = 'PlanWAT crawler update'
$Source = $env:PLANWAT_INSTALL_SOURCE
# The pins in .env are what was verified: image variables in the environment must not override them in compose.
# They only choose the images of a -NoVerify install (tests).
$ImageOverride = @{ 'planwat-crawler' = $env:PLANWAT_CRAWLER_IMAGE; 'planwat-crawler-egress' = $env:PLANWAT_EGRESS_IMAGE }
Remove-Item Env:PLANWAT_CRAWLER_IMAGE, Env:PLANWAT_EGRESS_IMAGE -ErrorAction SilentlyContinue

# Write-Host on purpose: these lines are for the person at the terminal, never part of a function's result.
function Say([string] $Text) { Write-Host $Text }
function Step([string] $Text) { Write-Host ''; Write-Host "== $Text" }
function Fail([string] $Text) { throw "Błąd: $Text" }
function Test-Command([string] $Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

function Update-SessionPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
}

# --- .env -----------------------------------------------------------------------------------------------------

function Get-EnvValue([string] $Key) {
    if (-not (Test-Path $EnvFile)) { return '' }
    $value = ''
    foreach ($line in [IO.File]::ReadAllLines($EnvFile)) {
        if ($line -match "^$Key=(.*)$") { $value = $Matches[1].Trim() }
    }
    return $value
}

function Set-EnvValue([string] $Key, [string] $Value) {
    New-Item -ItemType Directory -Force -Path $App | Out-Null
    $lines = @()
    if (Test-Path $EnvFile) { $lines = @([IO.File]::ReadAllLines($EnvFile)) }
    $out = New-Object Collections.Generic.List[string]
    $done = $false
    foreach ($line in $lines) {
        if ($line -match "^#? *$Key=") {
            if (-not $done) { $out.Add("$Key=$Value"); $done = $true }
        } else { $out.Add($line) }
    }
    if (-not $done) { $out.Add("$Key=$Value") }
    # LF and no BOM: compose and the wizard read this file too.
    [IO.File]::WriteAllText($EnvFile, (($out -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
    & icacls $EnvFile /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
}

# --- software -------------------------------------------------------------------------------------------------

function Test-Docker {
    if (-not (Test-Command docker)) { return $false }
    & docker compose version *> $null
    return $LASTEXITCODE -eq 0
}

function Test-Gh {
    if (-not (Test-Command gh)) { return $false }
    $line = (& gh --version | Select-Object -First 1)
    if ($line -match 'gh version ([0-9.]+)') { return ([version]$Matches[1]) -ge $GhMin }
    return $false
}

function Install-WithWinget([string] $Id) {
    if (-not (Test-Command winget)) {
        Fail 'brak winget: zainstaluj "Instalator aplikacji" (App Installer) ze Sklepu Microsoft i uruchom ponownie'
    }
    & winget install -e --id $Id --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) {  # the latter: already installed
        Fail "winget nie zainstalował $Id (kod $LASTEXITCODE)"
    }
    Update-SessionPath
}

function Start-Docker {
    & docker info *> $null
    if ($LASTEXITCODE -eq 0) { return }
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (Test-Path $desktop) { Start-Process $desktop }
    Say '  czekam na Docker Desktop (pierwsze uruchomienie trwa kilka minut)…'
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 4
        & docker info *> $null
        if ($LASTEXITCODE -eq 0) { return }
    }
    Fail 'Docker Desktop nie odpowiada. Jeśli instalował WSL2, uruchom ponownie komputer i ten skrypt jeszcze raz.'
}

function Enable-DockerAutostart {
    $settings = Join-Path $env:APPDATA 'Docker\settings-store.json'
    if (-not (Test-Path $settings)) { return }
    try {
        $json = Get-Content $settings -Raw | ConvertFrom-Json
        $json | Add-Member -NotePropertyName AutoStart -NotePropertyValue $true -Force
        [IO.File]::WriteAllText($settings, ($json | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding $false))
    } catch {
        Say '  (włącz w Docker Desktop: Settings → General → Start Docker Desktop when you sign in)'
    }
}

# --- releases and images --------------------------------------------------------------------------------------

function Get-LatestVersion {
    $release = Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 30
    return ($release.tag_name -replace '^v', '')
}

function Get-Channel {
    # -Channel, else PLANWAT_CHANNEL, else what .env remembers, else stable.
    $name = if ($Channel) { $Channel } elseif ($env:PLANWAT_CHANNEL) { $env:PLANWAT_CHANNEL } else { Get-EnvValue 'PLANWAT_CHANNEL' }
    if (-not $name) { $name = 'stable' }
    if ($name -notin @('stable', 'dev')) { Fail "nieznany kanał: $name (stable albo dev)" }
    if ($Version -and $name -eq 'dev') { Fail '-Version dotyczy kanału stable' }
    return $name
}

function Resolve-Release([string] $Name) {
    # Where the files come from (Ref), which images (Tag), and what to call it (Label).
    if ($Name -eq 'dev') {
        $dev = ''
        try { $dev = (Invoke-RestMethod -UseBasicParsing -Uri "https://raw.githubusercontent.com/$Repo/dev/package.json" -TimeoutSec 30).version } catch { $dev = '' }
        return @{ Channel = 'dev'; Ref = 'dev'; Tag = 'dev'; Label = $(if ($dev) { "dev ($dev)" } else { 'dev' }) }
    }
    $ver = if ($Version) { $Version } else { Get-LatestVersion }
    if (-not $ver) { Fail "nie mogę odczytać najnowszego wydania $Repo" }
    return @{ Channel = 'stable'; Ref = "v$ver"; Tag = $ver; Label = $ver }
}

function Get-ReleaseFiles($Release) {
    New-Item -ItemType Directory -Force -Path $App | Out-Null
    if ($Source) {
        Copy-Item (Join-Path $Source 'tools/volunteer/compose.volunteer.yml') "$App\compose.yml.new" -Force
        Copy-Item (Join-Path $Source 'tools/volunteer/install.ps1') "$CommandFile.new" -Force
    } else {
        $raw = "https://raw.githubusercontent.com/$Repo/$($Release.Ref)/tools/volunteer"
        try { Invoke-WebRequest -UseBasicParsing -Uri "$raw/compose.volunteer.yml" -OutFile "$App\compose.yml.new" }
        catch {
            if ($Release.Channel -eq 'stable') { Fail "wydanie $($Release.Label) nie ma jeszcze crawlera wolontariusza; do czasu wydania użyj -Channel dev" }
            Fail "nie mogę pobrać compose.yml z $($Release.Ref)"
        }
        try { Invoke-WebRequest -UseBasicParsing -Uri "$raw/install.ps1" -OutFile "$CommandFile.new" }
        catch { Copy-Item $PSCommandPath "$CommandFile.new" -Force }
    }
}

function Complete-ReleaseFiles {
    if (Test-Path "$App\compose.yml") { Copy-Item "$App\compose.yml" "$App\compose.yml.prev" -Force }
    Move-Item "$App\compose.yml.new" "$App\compose.yml" -Force
    if (Test-Path "$CommandFile.new") { Move-Item "$CommandFile.new" $CommandFile -Force }
    $shimDir = Split-Path $Shim
    if (Test-Path $shimDir) {
        Set-Content -Path $Shim -Encoding Ascii -Value "@powershell -NoProfile -ExecutionPolicy Bypass -File `"$CommandFile`" %*"
    }
}

function Invoke-Compose {
    # Never captured: the wizard, logs and status talk to the terminal. Callers read $LASTEXITCODE.
    & docker compose --project-name planwat-crawler --project-directory $App -f "$App\compose.yml" @args
}

function Get-RunningServices {
    & docker compose --project-name planwat-crawler --project-directory $App -f "$App\compose.yml" ps --status running --services
}

function Test-Healthy {
    # Both services running, never restarted since they were created, and not unhealthy.
    foreach ($service in @('crawler', 'egress')) {
        $id = & docker compose --project-name planwat-crawler --project-directory $App -f "$App\compose.yml" ps -q $service |
            Select-Object -First 1
        if (-not $id) { return $false }
        $state = & docker inspect --format '{{.State.Status}} {{.RestartCount}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' $id
        if ($LASTEXITCODE -ne 0 -or "$state" -match 'unhealthy' -or "$state" -notmatch '^running 0( |$)') { return $false }
    }
    return $true
}

function Get-VerifiedImages([string] $Ver) {
    $pins = @{}
    if ($NoVerify) {
        Say 'Uwaga: pomijam weryfikację pochodzenia obrazów (-NoVerify)'
        $pins['planwat-crawler'] = if ($ImageOverride['planwat-crawler']) { $ImageOverride['planwat-crawler'] } else { "ghcr.io/kilerdevs/planwat-crawler:$Ver" }
        $pins['planwat-crawler-egress'] = if ($ImageOverride['planwat-crawler-egress']) { $ImageOverride['planwat-crawler-egress'] } else { "ghcr.io/kilerdevs/planwat-crawler-egress:$Ver" }
        return $pins
    }
    $token = Get-EnvValue 'PLANWAT_FORK_TOKEN'
    if (-not $token) { Fail 'brak tokenu w .env (potrzebny do weryfikacji obrazów): planwat-crawler setup' }
    foreach ($name in $Images) {
        $ref = "ghcr.io/kilerdevs/${name}:$Ver"
        Say "  pobieram $ref"
        & docker pull -q $ref | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "nie mogę pobrać $ref" }
        $pinned = (& docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' $ref) |
            Where-Object { $_ -like "ghcr.io/kilerdevs/$name@sha256:*" } | Select-Object -First 1
        if (-not $pinned) { Fail "nie znam skrótu (digest) obrazu $ref" }
        $env:GH_TOKEN = $token
        $env:GH_PROMPT_DISABLED = '1'
        & gh attestation verify "oci://$pinned" --repo $Repo --signer-workflow $Signer *> "$App\verify.log"
        $ok = $LASTEXITCODE -eq 0
        Remove-Item Env:GH_TOKEN
        if (-not $ok) {
            Get-Content "$App\verify.log" -TotalCount 5 | ForEach-Object { Say $_ }
            Fail "obraz $pinned NIE przeszedł weryfikacji pochodzenia; nic nie zostało zmienione"
        }
        Say "  ✓ ${name}: zbudowany przez crawler-image.yml w $Repo ($pinned)"
        $pins[$name] = $pinned
    }
    return $pins
}

function Set-Pins($Pins) {
    Set-EnvValue 'PLANWAT_PREVIOUS_CRAWLER_IMAGE' (Get-EnvValue 'PLANWAT_CRAWLER_IMAGE')
    Set-EnvValue 'PLANWAT_PREVIOUS_EGRESS_IMAGE' (Get-EnvValue 'PLANWAT_EGRESS_IMAGE')
    Set-EnvValue 'PLANWAT_CRAWLER_IMAGE' $Pins['planwat-crawler']
    Set-EnvValue 'PLANWAT_EGRESS_IMAGE' $Pins['planwat-crawler-egress']
}

# --- identity -------------------------------------------------------------------------------------------------

function Read-Identity {
    $login = if ($env:PLANWAT_LOGIN) { $env:PLANWAT_LOGIN } else { Get-EnvValue 'PLANWAT_LOGIN' }
    $token = if ($env:PLANWAT_FORK_TOKEN) { $env:PLANWAT_FORK_TOKEN } else { Get-EnvValue 'PLANWAT_FORK_TOKEN' }
    while ($login -notmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,38}$') { $login = Read-Host 'Twój login na GitHubie' }
    Set-EnvValue 'PLANWAT_LOGIN' $login
    if (-not $token) {
        Say ''
        Say 'Crawler pracuje na Twoim forku projektu i wypycha do niego paczki tokenem, który widzi tylko ten fork.'
        Say "1. Jeśli nie masz jeszcze forka, utwórz go (Create fork): https://github.com/$Repo/fork"
        Say '2. Utwórz token (formularz jest częściowo wypełniony):'
        Say "   https://github.com/settings/personal-access-tokens/new?name=PlanWAT+crawler&target_name=$login&expires_in=90&contents=write"
        Say "   Repository access: Only select repositories → $login/PlanWAT (Twój fork)."
        Say '   Permissions → Repository permissions → Contents: Read and write. Nic więcej.'
        while ($token -notlike 'github_pat_*') {
            $secure = Read-Host '3. Wklej token (github_pat_…)' -AsSecureString
            $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
            if ($token -like 'ghp_*' -or $token -like 'gho_*') { Say '  To token klasyczny/OAuth: potrzebny fine-grained (github_pat_…).' }
        }
    }
    Set-EnvValue 'PLANWAT_FORK_TOKEN' $token
}

# --- scheduled updates ----------------------------------------------------------------------------------------

function Enable-AutoUpdate {
    Set-EnvValue 'PLANWAT_AUTO_UPDATE' '1'
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$CommandFile`" update -Auto"
    $trigger = New-ScheduledTaskTrigger -Daily -At 4am -RandomDelay (New-TimeSpan -Hours 3)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Say '  ✓ automatyczne aktualizacje: raz dziennie, tylko zweryfikowane obrazy (planwat-crawler autoupdate off wyłącza)'
}

function Disable-AutoUpdate {
    Set-EnvValue 'PLANWAT_AUTO_UPDATE' '0'
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Say '  automatyczne aktualizacje wyłączone; crawler zgłosi w logu nową wersję (planwat-crawler update)'
}

# --- commands -------------------------------------------------------------------------------------------------

function Install-Crawler {
    $plan = @()
    if (-not (Test-Docker)) { $plan += '  - Docker Desktop (winget; przy pierwszej instalacji także WSL2)' }
    if (-not $NoVerify -and -not (Test-Gh)) { $plan += "  - GitHub CLI >= $GhMin (winget; tylko do weryfikacji obrazów)" }
    Say 'PlanWAT: instalacja crawlera wolontariusza (Windows)'
    $chan = Get-Channel
    Say "Katalog: $App, polecenie: planwat-crawler, kanał: $chan"
    if ($plan) { Say 'Do zainstalowania:'; $plan | ForEach-Object { Say $_ } } else { Say 'Potrzebne programy już są.' }
    Say 'Potem: obrazy z weryfikacją pochodzenia, kreator konfiguracji, start i codzienne aktualizacje.'
    if ($Check) { return }
    if (-not $Yes) {
        $answer = Read-Host 'Kontynuować? [T/n]'
        if ($answer -and $answer -notmatch '^(t|tak|y|yes)$') { Fail 'przerwano' }
    }
    if (-not (Test-Docker)) { Step 'Docker Desktop'; Install-WithWinget 'Docker.DockerDesktop' }
    if (-not $NoVerify -and -not (Test-Gh)) { Step 'GitHub CLI'; Install-WithWinget 'GitHub.cli' }
    Start-Docker
    Enable-DockerAutostart
    Step 'Wydanie'
    $release = Resolve-Release $chan
    Say "  wersja $($release.Label)"
    Get-ReleaseFiles $release
    Complete-ReleaseFiles
    Set-EnvValue 'PLANWAT_CHANNEL' $chan
    Step 'Konto i token'
    Read-Identity
    Step 'Obrazy'
    Set-Pins (Get-VerifiedImages $release.Tag)
    Set-EnvValue 'PLANWAT_VERSION' $release.Label
    Step 'Konfiguracja'
    $extra = @()
    if ($env:PLANWAT_SETUP_ARGS) { $extra = $env:PLANWAT_SETUP_ARGS -split ' ' }
    Invoke-Compose run --rm -v "${App}:/config" crawler setup --env /config/.env --keep-token --login (Get-EnvValue 'PLANWAT_LOGIN') @extra
    if ($LASTEXITCODE -ne 0) { Fail 'kreator przerwany; uruchom ponownie: planwat-crawler setup' }
    Step 'Diagnostyka'
    # Not being in the registry yet is expected here (a warning); anything else marked ✗ is said again at the end.
    Invoke-Compose run --rm crawler doctor --no-probe --installing
    $diagnosed = $LASTEXITCODE -eq 0
    if ((Get-EnvValue 'PLANWAT_AUTO_UPDATE') -eq '0') { Disable-AutoUpdate } else { Enable-AutoUpdate }
    if (-not $NoStart) {
        Step 'Start'
        Invoke-Compose up -d
    }
    Say ''
    if (-not $diagnosed) {
        Say 'Uwaga: diagnostyka zgłosiła problemy (✗ wyżej): crawler nie pomoże, dopóki ich nie poprawisz; potem: planwat-crawler doctor'
        Say 'Przydatne polecenia:'
    } elseif (-not $NoStart) {
        Say '✓ Crawler działa (Docker Desktop musi być uruchomiony). Przydatne polecenia:'
    } else {
        Say '✓ Zainstalowano (bez startu: planwat-crawler start).'
    }
    Say '  planwat-crawler status     co robi teraz i co koordynator powiedział o ostatniej paczce'
    Say '  planwat-crawler logs       dziennik na żywo'
    Say '  planwat-crawler doctor     pełna diagnostyka z podpowiedziami'
}

function Update-Crawler {
    if ($Auto -and (Get-EnvValue 'PLANWAT_AUTO_UPDATE') -eq '0') { return }
    $log = Join-Path $App 'update.log'
    if ($Auto) { Start-Transcript -Path $log -Append | Out-Null }
    try {
        $installed = Get-EnvValue 'PLANWAT_VERSION'
        $was = Get-EnvValue 'PLANWAT_CHANNEL'
        $chan = Get-Channel
        $release = Resolve-Release $chan
        $forced = [bool]($Version -or $Channel)
        # A release number says enough on stable; anything else (dev, a channel switch) is decided by the digests.
        if (-not $forced -and $chan -eq 'stable' -and (-not $was -or $was -eq 'stable') -and $installed -match '^\d+\.\d+\.\d+$' `
                -and ([version]$installed -ge [version]$release.Tag)) {
            Say "Masz najnowszą wersję ($installed)."; return
        }
        Start-Docker
        Get-ReleaseFiles $release
        $pins = Get-VerifiedImages $release.Tag
        if (-not $forced -and $pins['planwat-crawler'] -eq (Get-EnvValue 'PLANWAT_CRAWLER_IMAGE') -and
                $pins['planwat-crawler-egress'] -eq (Get-EnvValue 'PLANWAT_EGRESS_IMAGE')) {
            Remove-Item "$App\compose.yml.new", "$CommandFile.new" -ErrorAction SilentlyContinue
            Say "Masz najnowszą wersję ($($release.Label))."; return
        }
        $ver = $release.Label
        Say "Aktualizacja $installed → $ver"
        Set-Pins $pins
        Complete-ReleaseFiles
        Set-EnvValue 'PLANWAT_CHANNEL' $chan
        # Fresh containers, so a restart counted below can only be the new version's.
        Invoke-Compose up -d --remove-orphans --force-recreate
        $why = ''
        if ($LASTEXITCODE -ne 0) { $why = 'nowa wersja nie wystartowała' }
        else {
            Say '  sprawdzam, czy nowa wersja działa…'
            Start-Sleep -Seconds 90
            if (-not (Test-Healthy)) { $why = 'nowa wersja nie działa (zatrzymuje się, restartuje albo jest unhealthy)' }
        }
        if (-not $why) {
            Set-EnvValue 'PLANWAT_VERSION' $ver
            Say "✓ zaktualizowano do $ver"
        } else {
            Say "Uwaga: $why; wracam do poprzedniej"
            Set-EnvValue 'PLANWAT_CRAWLER_IMAGE' (Get-EnvValue 'PLANWAT_PREVIOUS_CRAWLER_IMAGE')
            Set-EnvValue 'PLANWAT_EGRESS_IMAGE' (Get-EnvValue 'PLANWAT_PREVIOUS_EGRESS_IMAGE')
            if (Test-Path "$App\compose.yml.prev") { Copy-Item "$App\compose.yml.prev" "$App\compose.yml" -Force }
            if ($was) { Set-EnvValue 'PLANWAT_CHANNEL' $was }
            Invoke-Compose up -d --remove-orphans --force-recreate
            if ($LASTEXITCODE -ne 0) { Say 'Uwaga: poprzednia wersja też nie wstaje: planwat-crawler doctor' }
            Fail "aktualizacja do $ver cofnięta (zostaje $installed)"
        }
    } finally {
        if ($Auto) { Stop-Transcript | Out-Null }
    }
}

function Remove-Crawler {
    # This cannot be undone: only an explicit yes (or -Yes / --yes) agrees; an empty answer or no input does not.
    if (-not $Yes -and $Argument -notin @('--yes', '-y')) {
        $answer = Read-Host 'Usunąć crawler, jego dane i harmonogram aktualizacji? [t/N]'
        if (-not $answer -or $answer -notmatch '^(t|tak|y|yes)$') { Fail 'przerwano (nic nie usunięto)' }
    }
    if (Test-Path "$App\compose.yml") { Invoke-Compose down -v --remove-orphans }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $App -ErrorAction SilentlyContinue
    Remove-Item -Force $Shim, $CommandFile -ErrorAction SilentlyContinue
    Say '✓ Usunięto. Dokończ na GitHubie: usuń token (https://github.com/settings/personal-access-tokens)'
    Say '  i, jeśli chcesz, gałąź crawl ze swojego forka.'
}

function Invoke-InCrawler {
    if (@(Get-RunningServices) -contains 'crawler') { Invoke-Compose exec -T crawler /app/tools/volunteer/entrypoint.sh @args }
    else {
        Say 'Uwaga: crawler nie działa (planwat-crawler start); poniżej ostatni zapisany stan, nie bieżący'
        Invoke-Compose run --rm crawler @args
    }
}

switch ($Command) {
    'install' { Install-Crawler }
    'update' { Update-Crawler }
    'uninstall' { Remove-Crawler }
    default {
        if (-not (Test-Path "$App\compose.yml")) { Fail "crawler nie jest zainstalowany ($App); uruchom install.ps1" }
        switch ($Command) {
            'status' { Invoke-InCrawler status }
            'doctor' { Invoke-InCrawler doctor }
            'logs' { Invoke-Compose logs -f --tail 200 $(if ($Argument -eq 'egress') { 'egress' } else { 'crawler' }) }
            'setup' { Invoke-Compose run --rm -v "${App}:/config" crawler setup --env /config/.env; Invoke-Compose up -d }
            'autoupdate' {
                if ($Argument -eq 'on') { Enable-AutoUpdate }
                elseif ($Argument -eq 'off') { Disable-AutoUpdate }
                else { Say ("automatyczne aktualizacje: " + $(if ((Get-EnvValue 'PLANWAT_AUTO_UPDATE') -eq '0') { 'wyłączone' } else { 'włączone' })) }
            }
            'start' { Start-Docker; Invoke-Compose up -d }
            'stop' { Invoke-Compose stop }
            'restart' { Invoke-Compose restart }
            'version' { Say "planwat-crawler $(Get-EnvValue 'PLANWAT_VERSION') (kanał $(Get-Channel))" }
            default { Fail "nieznane polecenie: $Command (status, logs, doctor, setup, update, autoupdate on|off, start, stop, restart, uninstall)" }
        }
    }
}

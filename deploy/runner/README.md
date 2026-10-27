# Runner projektu na VPS

Własny runner `refresh.yml` (etykiety `planwat` i `planwat-oracle`) razem z proxy wyjściowym, na jednej maszynie z Dockerem.
To wolniejszy, zawsze włączony runner projektu: każdy przebieg dzieli wydziały między niego a plebanię, gdy ta jest
włączona ([docs/REFRESH.md](../../docs/REFRESH.md#runnery-i-podział-pracy), `tools/refresh/fleet.json`). Zasady są te
same co w [docs/REFRESH.md](../../docs/REFRESH.md) („Własny runner”):

- runner działa w kontenerze jako użytkownik bez uprawnień, bez gniazda Dockera i bez montowań hosta;
- jego sieć (`inner`) nie ma trasy na zewnątrz: GitHub, PyPI i wydziały osiąga tylko przez egress
  ([docs/EGRESS.md](../../docs/EGRESS.md)), który przepuszcza wyłącznie te hosty;
- WCY blokuje adresy centrów danych, więc idzie zawsze przez pulę (`EGRESS_FAIL_CLOSED`), a pozostałe wydziały
  bezpośrednio. Gdy linia maszyny jest za ścianą, włącz opcjonalny relay Cloudflare (`PLANWAT_RELAY_*`,
  [docs/EGRESS.md](../../docs/EGRESS.md)): wtedy WLO, WEL, WML i WIG idą przez Worker, a WCY nadal przez pulę. WTC
  z zachodnich wyjść Cloudflare dostaje 403, więc zostaje z plebanią.
  Zanim użyjesz innej maszyny, sprawdź, które wydziały ją wpuszczają:

  ```sh
  docker run --rm --entrypoint python ghcr.io/kilerdevs/planwat-crawler:dev -c \
    "import sys; sys.path.insert(0,'/app/tools/volunteer'); import doctor; print(doctor.probe_faculties())"
  ```

  i dopasuj `EGRESS_DIRECT_FACULTY` w `compose.yml`.

## Instalacja

Na maszynie potrzebny jest Docker z Compose i ok. 1 GB RAM (przy 1 GB dodaj swap). Pliki: `deploy/runner/` i
`tools/egress/` w tym samym układzie katalogów co w repozytorium.

1. Settings → Actions → Runners → New self-hosted runner: skopiuj token rejestracji (ważny godzinę).
2. `cp .env.example .env`, wpisz `RUNNER_TOKEN`, wygeneruj `EGRESS_API_TOKEN` (`openssl rand -hex 24`), `chmod 600 .env`.
3. `docker compose up -d --build`. Runner rejestruje się przy pierwszym starcie (rejestracja zostaje w wolumenie
   `runner`); potem usuń `RUNNER_TOKEN` z `.env`.
4. Actions → *Refresh timetables* → Run workflow, wydział `wim`.

GUI egressu: `ssh -L 18080:127.0.0.1:18080 <host>`, potem <http://localhost:18080> (zaloguj się tokenem z `.env`).

## Relay Cloudflare (opcjonalnie)

Gdy ściana Incapsuli blokuje linię maszyny (27.10.2026 dotyczyło to WLO, WEL, WML, WTC i WIG), wdróż Worker według
[`tools/egress/cloudflare/README.md`](../../tools/egress/cloudflare/README.md) i wpisz do `.env`:

```sh
PLANWAT_RELAY_URL=https://planwat-egress.<konto>.workers.dev
PLANWAT_RELAY_TOKEN=...
# opcjonalnie: PLANWAT_RELAY_HOSTS=... (puste = domyślna lista hostów, "off" wyłącza relay)
EGRESS_DIRECT_HOSTS=planwat-egress.<konto>.workers.dev
```

Ostatnia linia jest ważna: egress musi przepuścić dokładnie ten hostname bezpośrednio, inaczej odpowie `403`. Nie wpisuj
tam całego `workers.dev`. WCY nadal idzie przez pulę (`EGRESS_FAIL_CLOSED`), bo Worker dostaje od niego `403`.

## Northflank

Ten sam obraz działa też jako darmowy kontener Northflank (runner `northflank` w
[`fleet.json`](../../tools/refresh/fleet.json)), bez egress: usługa budowana z repozytorium, Dockerfile
`/deploy/runner/Dockerfile.runner`, kontekst `/deploy/runner`, gałąź `master`, reguła ścieżek **Allow** `deploy/runner/**`
(inne pushe nie restartują runnera), bez portów. Zmienne środowiskowe (runtime): `RUNNER_REPO_URL`, `RUNNER_NAME=northflank`,
`RUNNER_LABELS=planwat,planwat-northflank` i `RUNNER_TOKEN` (sekret, ważny godzinę), bez `HTTP(S)_PROXY`. Opcjonalnie
`PLANWAT_RELAY_URL` i `PLANWAT_RELAY_TOKEN` (oraz `PLANWAT_RELAY_HOSTS`), jeśli kontener ma używać Workera. Kontener nie ma
wolumenu, więc rejestrację trzyma zmienna `RUNNER_STATE` (sekret): pliki rejestracji jako base64 z tar.gz, które
entrypoint odtwarza przy starcie, gdy ich brak, zamiast rejestrować runner od nowa. Po pierwszej rejestracji zapisz je
raz: `northflank exec service --cmd '/usr/local/bin/planwat-runner state' --shell-cmd 'bash -c'` wypisuje wartość
(nie pokazuj jej nikomu: to tożsamość runnera). Gdy runner zostanie usunięty w GitHubie albo zarejestrowany od nowa,
stara wartość przestaje działać: wpisz świeży `RUNNER_TOKEN`, a po starcie zapisz nowy `RUNNER_STATE`. Adres Google Cloud przechodzi
tylko przez ściany IOE, WIG i WIM (próba 27.10.2026); po włączeniu relaya Cloudflare może brać także WLO, WEL i WML
(`faculties` w `fleet.json` już je mają). WTC z zachodnich wyjść Workera dostaje 403, więc zostaje z plebanią, a WCY
nadal wymaga puli, której Northflank nie ma. Bez relaya usuń WLO, WEL i WML z listy.

## Utrzymanie

- Aktualizacja egressu albo obrazu runnera: podmień pliki, `docker compose up -d --build`. Sam runner aktualizuje się
  automatycznie w wolumenie.
- Ponowna rejestracja: `docker compose down`, `docker volume rm planwat-runner_runner`, nowy `RUNNER_TOKEN`, `up -d`.
  Etykiety bierze z `RUNNER_LABELS`; już zarejestrowanemu runnerowi zmienisz je w Settings → Actions → Runners.
- Logi: `docker compose logs -f runner` / `egress`.

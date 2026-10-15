<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Proxy wyjściowe (backend runnera)

**Jedno `HTTP_PROXY` dla runnera, z polityką dla każdego celu.**

[![Egress](https://github.com/kilerdevs/PlanWAT/actions/workflows/egress.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/egress.yml)
![Domyślnie](https://img.shields.io/badge/domy%C5%9Blnie-odmowa%20(403)-critical?style=flat)
![Porty](https://img.shields.io/badge/porty-443%20%C2%B7%2080-blue?style=flat)
![GUI](https://img.shields.io/badge/monitoring-LAN%20%3A18080-informational?style=flat)

</div>

Zastępuje rolę tinyproxy:

| Cel | Polityka |
|---|---|
| infrastruktura (GitHub, PyPI, listy proxy, … na równi z `allow.txt`) | bezpośrednie wyjście |
| wydziały (`*.wat.edu.pl`) | przez rotującą pulę publicznych proxy, inny adres wyjściowy na każde połączenie |
| cokolwiek innego | 403 (ta sama domyślna odmowa co w tinyproxy) |

<img src="diagrams/proxy-egress.svg" alt="Runner wysyła ruch przez proxy egress: infrastruktura bezpośrednio, strony wydziałów przez pulę proxy, reszta dostaje 403. Panel monitoringu w LAN odbiera raporty." width="760">

Dlaczego pula mieszka tutaj, a nie w `refresh.py`: kontener runnera nie ma bezpośredniej trasy na zewnątrz, wszystko przechodzi
przez warstwę proxy, która odrzuca kodem 403 wszystko spoza listy dozwolonych (także gołe adresy proxy). Proces w runnerze
*nie może dotrzeć* do publicznych proxy, więc rotacja musi odbywać się w warstwie wyjścia. `refresh.py` potrzebował tylko
ponowień z odczekaniem (`--retries/--retry-backoff`) i raportu przebiegu dla GUI.

## Części

- `tools/egress/pool.py`: pula proxy (wzorzec z DeadDropMGMT). Pobiera te same 9 list proxy z GitHub (proxifly, monosans,
  thespeedx, roosterkid), sprawdza kandydatów *przez nich samych* na stronie indeksu wydziału (bez zewnętrznego sędziego: 200 +
  znacznik = zdrowy), sortuje ok → nowe → błąd według opóźnienia i zapisuje `pool.json`. Uszkodzone proxy odpoczywają 15 minut.
- `tools/egress/server.py`: proxy przekazujące `:8888` (CONNECT i zwykłe HTTP, tylko porty 443/80) z łączeniem łańcuchowym
  HTTP/SOCKS5/SOCKS4a, plus GUI monitoringu w sieci LAN `:8080` (na hoście `:18080`, bo `:8080` zajmuje cAdvisor na hoście runnera)
  (`/` panel, `GET /api/status`, `POST /api/run` skrzynka raportów, `POST /api/refresh` wymuszenie odświeżenia). Żądania POST
  niosą `Authorization: Bearer $EGRESS_API_TOKEN`, gdy ustawiono `EGRESS_API_TOKEN`.
- `Dockerfile.egress`, `requirements.txt` (curl_cffi, ta sama wersja co w odświeżaniu), `compose.fragment.yml` (fragment usługi
  do pliku compose plebanii).
- `tools/egress/prometheus-alerts.yml`, `tools/egress/blackbox-snippet.yml`: gotowy szablon alertów i sondy Blackbox dla
  Prometheusa na maszynie (jeszcze niepodłączony).

Polityka pustej puli to świadomy wybór operatora „fail-open”: ruch do wydziałów idzie bezpośrednio, a GUI pokazuje tryb DIRECT
(`PLANWAT_EGRESS_DIRECT_FALLBACK=1`). Ustaw `0`, by uzyskać „fail-closed” w stylu DeadDropMGMT (żądania do wydziałów dostają 403, aż pula
wróci do zdrowia).

## GUI monitoringu

Tylko LAN: `http://<host-egress>:18080/` (kontener `:8080`; zawęź bind, jeśli maszyna jest bardziej wystawiona niż domowa sieć LAN).
Odświeża się automatycznie co 30 s. Pokazuje:

- tryb ROTATING vs DIRECT, rozmiar, zdrowie i medianę opóźnienia puli, liczniki fallbacków i odmów;
- wiersze ROTATING/DIRECT dla każdego hosta (`/api/status` `.hosts.<host>`: liczba `verified` i fallbacki; 0 zweryfikowanych =
  wydział jedzie bezpośrednio);
- tabelę proxy (adres, stan, opóźnienie, źródło);
- ostatnie przebiegi odświeżania zgłoszone przez `refresh.py` (`started/ended/exit` + dla wydziału sprawdzone/zmienione/
  pominięte/zablokowane, a przy masowym pomijaniu także `degraded`). Raporty są też zapisywane w `/data/runs.json`.

Sprawdzenie stanu: `GET /api/status` (200 = GUI działa; dodaj jako `healthcheck:` w compose, a samo „unhealthy” nigdy nie
restartuje kontenera, więc połącz z mechanizmem w stylu autoheal).

`refresh.py` raportuje najlepszym wysiłkiem przez sieć wewnętrzną (`PLANWAT_EGRESS_STATUS`, domyślnie
`http://<egress-ip>:8080/api/run`, puste wyłącza). Martwe GUI nigdy nie psuje crawla. Statystyki przebiegu dla wydziału
trafiają też do `refresh-state.json` (`faculties.<nazwa>.run`). Przebieg pogorszony, ale niezablokowany otwiera lub aktualizuje
zgłoszenie `zdegradowane` (zob. akcję odświeżania).

Alerty (szablon, jeszcze niepodłączony): `prometheus-alerts.yml` (egress nie działa 5 min: krytyczny, host utknął w DIRECT 2 h,
pula żywych < 5, dysk maszyny > 85%, runner offline) zasilany sondą `blackbox-snippet.yml` (`http_2xx`, 60 s,
`http://<host-egress>:18080/api/status`).

## Lista kontrolna wdrożenia (host runnera): NIE uruchamiać bez zgody

1. `scp -r tools/egress <użytkownik>@<host>:/opt/planwat-egress/` (wymaga SSH z hasłem: przełącz `PasswordAuthentication` w
   `/etc/ssh/sshd_config.d/00-hardening.conf` i `systemctl restart ssh`).
2. Wstaw `compose.fragment.yml` do `<katalog runnera>/compose.yml` (dodaje `egress` pod `<egress-ip>`, a tinyproxy zostaje
   nietknięty jako wycofanie).
3. `docker compose up -d --build egress`, otwórz `:18080` i poczekaj na odświeżenie puli → ROTATING.
4. Przełączenie: `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy` runnera → `http://<egress-ip>:8888` z `NO_PROXY` obejmującym
   podsieć wewnętrzną (`localhost,127.0.0.1,<inner-subnet>`, żeby zapytania GUI i statusu omijały proxy),
   `docker compose up -d runner`.
5. Uruchom mały przebieg (`--faculty wcy --limit 5 --dry-run`) i obserwuj tryb w GUI oraz tabelę przebiegów.
6. Wycofanie (przy jakichkolwiek wątpliwościach): skieruj runner z powrotem na `http://<proxy-ip>:8888`, `up -d runner`.

Zmiana `allow.txt` nie jest potrzebna: pobieranie list i sprawdzanie dzieje się wewnątrz kontenera egress na jego własnej
bezpośredniej trasie, a ruch odświeżania wciąż płynie przez jedno proxy „dozwolone w duchu”, które egzekwuje tę samą politykę.

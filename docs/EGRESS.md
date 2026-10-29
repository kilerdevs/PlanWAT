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
| relay Cloudflare (opcjonalny Worker, zob. niżej) | bezpośrednie wyjście tylko wtedy, gdy jego dokładny hostname jest w `EGRESS_DIRECT_HOSTS`; inaczej 403 |
| wydziały (`*.wat.edu.pl`) | przez rotującą pulę publicznych proxy, inny adres wyjściowy na każde połączenie; hosty z listy `EGRESS_DIRECT_FACULTY` idą jednak bezpośrednio, bo to wyjścia puli dostają od nich blokady, a linia domowa zwykle je serwuje |
| cokolwiek innego | 403 (ta sama domyślna odmowa co w tinyproxy) |

<img src="diagrams/proxy-egress.svg" alt="Runner wysyła ruch przez proxy egress: infrastruktura bezpośrednio, strony wydziałów przez pulę proxy, reszta dostaje 403. Panel monitoringu w LAN odbiera raporty." width="760">

Dlaczego pula mieszka tutaj, a nie w `refresh.py`: kontener runnera nie ma bezpośredniej trasy na zewnątrz, wszystko przechodzi
przez warstwę proxy, która odrzuca kodem 403 wszystko spoza listy dozwolonych (także gołe adresy proxy). Proces w runnerze
*nie może dotrzeć* do publicznych proxy, więc rotacja musi odbywać się w warstwie wyjścia. `refresh.py` potrzebował tylko
ponowień z odczekaniem (`--retries/--retry-backoff`) i raportu przebiegu dla GUI. Od 17.10.2026 crawl raportuje też blokady
(`POST /api/block`): w tunelu CONNECT proxy nie widzi strony blokady, ale crawler ją czyta, więc mówi proxy, którego celu
dotyczyła — a to wycofuje wyjście z ostatniego tunelu do tego hosta. Bez tego pula wierzyła, że oznaczone wyjście nadal działa
(tunel się przecież udał), i podawała je dalej, dopóki cały wydział nie stanął.

## Części

- `tools/egress/pool.py`: pula proxy (wzorzec z DeadDropMGMT). Pobiera te same 8 list proxy z GitHub (proxifly, monosans,
  thespeedx, roosterkid) i sprawdza kandydatów *przez nich samych*: Round 1 to neutralny kafelek OSM, Round 2 — strona indeksu
  wydziału. Zdrowy wynik to 200, odpowiedni rozmiar, dodatni znacznik treści i brak znanych stron blokad (WAF potrafi oddać
  duże 200), więc fałszywe „żywe” nie trafia do puli. Wybór sortuje ok → nowe → błąd według opóźnienia i zapisuje `pool.json`.
  Pula odświeża się co 4 h, sprawdza do 240 kandydatów na 32 wątkach i dorabia do 56 weryfikacji na host; uszkodzone proxy
  odpoczywają 10 minut, a po całkowitej awarii list mechanizm utrzymania wraca po 5 minutach, nie po 4 h. Samo niskie pokrycie
  hosta (np. WCY za WAF-em) uruchamia ponowne odświeżenie najwyżej co 10 minut, więc nie zapętla pobierania list i sond. Osiem niepowodzeń
  w 2 minuty wyłącza wyjścia tylko dla jednego hosta (sukces zdejmuje blokadę od razu), a wybór z warstwy zweryfikowanej
  rotuje między wyjściami — jedno szybkie proxy nie dostaje całego crawla, więc nie zostaje przez to oznaczone przez WAF.
  Wyjście zweryfikowane dla hosta szereguje jego własny wynik, nie pudła na innych wydziałach. Werdykty per host, blokady
  i wezwania do leczenia dotyczą tylko znanych hostów wydziałów: wymyślone nazwy `*.wat.edu.pl` od kodu zadania nie rozdmuchują
  puli ani nie wyłączają wyjść. Znaczniki czasu monotonicznego nie są wczytywane z `pool.json` (po restarcie maszyny
  „odpoczynek” liczy się od zegara ściennego).
- `tools/egress/server.py`: proxy przekazujące `:8888` (CONNECT i zwykłe HTTP, tylko porty 443/80, nazwa celu sprowadzona do małych
  liter bez kropki na końcu i odrzucana, gdy nie jest poprawną nazwą DNS) z łączeniem łańcuchowym
  HTTP/SOCKS5/SOCKS4a (w tym adresy IPv6 w odpowiedzi SOCKS5), plus GUI monitoringu w sieci LAN `:8080` (na hoście `:18080`,
  bo `:8080` zajmuje cAdvisor na hoście runnera) (`/` panel, `GET /api/status`, `POST /api/run` skrzynka raportów,
  `POST /api/block` zgłoszenie blokady (wycofuje wyjście), `POST /api/progress` postęp przebiegu na żywo, `GET /api/progress`
  jego podsumowanie dla GUI, `POST /api/refresh` wymuszenie odświeżenia — 409, gdy puli nie ma, `POST /login` logowanie
  przeglądarki). Żądania przyjmują `X-Token` albo `Authorization: Bearer $EGRESS_API_TOKEN` (crawler wysyła oba; spacje wokół
  wartości w `.env` się nie liczą). Z ustawionym tokenem chronione są też odczyty: panel, `GET /api/progress` i pełny
  `GET /api/status` (bez tokenu ten ostatni odpowiada tylko `{"ok":true,"auth":"required"}`, więc sondy i healthchecki działają
  dalej). Przeglądarka loguje się formularzem panelu i dostaje ciasteczko sesji (pochodne tokenu, `HttpOnly`,
  `SameSite=Strict`), które otwiera tylko odczyty — API POST zawsze wymaga tokenu w nagłówku. Bez tokenu API jest otwarte
  (egress ostrzega o tym w logu przy starcie), więc port GUI musi wtedy zostać na `localhost`. Token jest sprawdzany przed
  odczytem ciała, ciało ma sufit 256 KiB, a liczba połączeń jest ograniczona (proxy: `EGRESS_MAX_CONNECTIONS`, domyślnie 96;
  GUI: stałe 32). Tunel kończy się po 120 s ciszy (i najpóźniej po 600 s w ogóle) i zachowuje półzamknięcie, więc klient,
  który skończył wysyłać, wciąż odbiera całą odpowiedź.
- `tools/refresh/relay.py`: strona crawlująca relayu (opcjonalna): zawija sesję `curl_cffi` i wysyła `GET` do Workera
  tylko dla hostów z `PLANWAT_RELAY_HOSTS`, zachowując oryginalny URL w `RelayResponse.url`, więc sterowniki dalej budują
  adresy grup ze swojej bazy, a odświeżanie warunkowe i wykrywanie blokad widzą zwykłą odpowiedź upstreamu. Bez
  `PLANWAT_RELAY_URL` moduł jest no-opem.
- `tools/egress/cloudflare/`: Worker Cloudflare (`worker.js`, `wrangler.toml`, `README.md`) z tokenem, dokładną listą
  hostów i bezpiecznym prowadzeniem przekierowań; wdrażany osobno, poza obrazem egressu.
- `Dockerfile.egress`, `requirements.txt` (curl_cffi, ta sama wersja co w odświeżaniu), `compose.fragment.yml` (fragment usługi
  do pliku compose plebanii).
- `tools/egress/prometheus-alerts.yml`, `tools/egress/blackbox-snippet.yml`: gotowy szablon alertów i sondy Blackbox dla
  Prometheusa na maszynie (jeszcze niepodłączony).

Polityka pustej puli to świadomy wybór operatora „fail-open”: ruch do wydziałów idzie bezpośrednio, a GUI pokazuje tryb DIRECT
(`PLANWAT_EGRESS_DIRECT_FALLBACK=1`). Ustaw `0`, by uzyskać „fail-closed” w stylu DeadDropMGMT (żądania do wydziałów dostają 403, aż pula
wróci do zdrowia). `EGRESS_FAIL_CLOSED` pozwala zawęzić to do wybranych hostów (nazwy rozdzielone przecinkami lub spacjami;
`1`, `true` albo `all` obejmuje wszystkie hosty `*.wat.edu.pl` jadące przez pulę, czyli spoza `EGRESS_DIRECT_FACULTY`): wpisany
host nigdy nie spada na linię domową, nawet przy fail-open — także wtedy, gdy ktoś wpisze go również na listę
`EGRESS_DIRECT_FACULTY` albo włączy `EGRESS_POOL=off` (wtedy wygrywa fail-closed, a egress ostrzega w logu przy starcie).
Wdrożenie produkcyjne wpisuje tam `planzajec.wcy.wat.edu.pl`, bo ten host jest blokowany właśnie z linii domowej i działa tylko
przez pulę. Bez zdrowego wyjścia taki host dostaje 403, a GUI pokazuje go jako `FAIL-CLOSED` (tryb puli
`FAIL-CLOSED (pula pusta)`), nie jako DIRECT.

Lista `EGRESS_DIRECT_FACULTY` (nazwy hostów rozdzielone przecinkami lub spacjami, ustawiana w `compose.yml`) wyłącza wybrane
hosty wydziałów z puli. Publiczne wyjścia dostają od nich blokady Incapsuli, a linia domowa zwykle je serwuje — ale 27.10.2026
ta sama ściana zamknęła też linię domową `77.222.244.159` dla WTC, WLO, WEL, WML, WIG i WCY (WIM i IOE nadal działały).
Dlatego w typowym wdrożeniu WEL i WIG idą przez relay Cloudflare (niżej), a WLO, WML i WTC zostają na linii plebanii, gdy
jest czysta (z zachodnich wyjść Workera dostają 403); `EGRESS_DIRECT_FACULTY` zostaje jako ścieżka bezpośrednia dla
maszyny, której linia jest czysta. WCY jest wyjątkiem: jego blokuje linia domowa, więc zostaje na puli
(`EGRESS_FAIL_CLOSED`). Host z listy pokazuje w GUI tryb `DIRECT (lista)`. Tylko hosty spoza tej listy są sprawdzane
i weryfikowane przez pulę. `EGRESS_POOL=off` to tryb wolontariusza: każdy host wydziału (także dodany później do
`faculty_targets()`) idzie bezpośrednio (w GUI `DIRECT (bez puli)`), a pula nie pobiera list, nie sonduje nikogo i nie wydaje
żadnego wyjścia, nawet ze starego `pool.json`. To przełącznik, a nie ręcznie przepisana lista hostów, która rozjeżdża się po
dodaniu wydziału.

## Relay Cloudflare dla ścian, których pula nie przechodzi

Pula nie ma wyjścia dla każdego wydziału: pomiar z 27.10.2026 na 200 kandydatach dał 37 żywych i 32 zweryfikowane, z pokryciem
WLO 1, WEL 14, WML 17, a WTC, WIG i WCY 0. Cloudflare Worker pobiera strony z adresów, które ściana wpuszcza. Sprawdzone
29.10.2026 z AMS i FRA: WEL i WIG (indeksy, listingi i grupy) przechodzą przez Workera, a strony planów WLO, WML i WTC
dostają 403 (z WLO przechodzi tylko strona główna, nie `planzajec/zima/index.xml`). Wcześniejszy pomiar z polskiej linii
27.10.2026 dawał WLO/WEL, WML i WIG po 200, ale zachodnie wyjścia Cloudflare są blokowane — dlatego WLO, WML i WTC
zostają z plebanią, której linia domowa jest czysta, a relay jest dla WEL i WIG.
Relay jest opcjonalny i domyślnie wyłączony: bez `PLANWAT_RELAY_URL` crawler zachowuje się dokładnie jak wcześniej.

Przepływ:

```text
runner -> egress (bezpośrednio, hostname Workera w EGRESS_DIRECT_HOSTS) -> Worker -> wydział
```

Runner wysyła `GET <PLANWAT_RELAY_URL>?url=<zakodowany URL>` z `Authorization: Bearer <token>`, a Worker oddaje status,
`ETag`/`Last-Modified` i treść upstreamu. `RelayResponse.url` to oryginalny adres wydziału, więc względne linki i adresy grup
nie zmieniają się. Blokady zgłaszane przez crawler nie trafiają do `POST /api/block` dla hostów relayowanych: żadne wyjście
puli nie brało w nich udziału, więc nie ma czego degradować. Gdy upstream odpowie `403`, Worker usuwa zapamiętane
ciasteczka hosta i ponawia żądanie dwa razy z czystą sesją: z różnych wyjść Cloudflare ta sama strona raz przechodzi, a raz
nie, więc pojedynczy `403` nie jest jeszcze ścianą.

Konfiguracja:

| Zmienna | Gdzie | Znaczenie |
|---|---|---|
| `PLANWAT_RELAY_URL` | runner | root Workera, np. `https://planwat-egress.<konto>.workers.dev`; puste = relay wyłączony |
| `PLANWAT_RELAY_TOKEN` | runner + sekret Workera | token bearer; ten sam po obu stronach |
| `PLANWAT_RELAY_HOSTS` | runner (opcjonalnie) | hosty relayowane, rozdzielone przecinkami/spacjami; puste = domyślna lista hostów z `relay.py`, `off` = wyłącz relay bez zmiany URL |
| `EGRESS_DIRECT_HOSTS` | egress | dokładny hostname Workera (bez `https://`), żeby egress przepuścił go bezpośrednio; nie wpisuj całego `workers.dev`, chyba że świadomie |

Wdrożenie Workera: [tools/egress/cloudflare/README.md](../tools/egress/cloudflare/README.md). Po `wrangler deploy` ustaw sekret
`PLANWAT_RELAY_TOKEN`, wpisz adres i token do `.env` runnera, a hostname Workera do `EGRESS_DIRECT_HOSTS` w `.env` egressu
(`deploy/runner/.env.example` ma wszystkie cztery miejsca). Sprawdzenie: `curl` z tokenem na
`?url=https://wml.wat.edu.pl/` ma zwrócić 200, bez tokenu 401, a host spoza listy 403.

Darmowy plan Cloudflare wystarcza: 100 000 żądań dziennie i 10 ms CPU na żądanie (stan 27.10.2026). Jeden pobrany dokument
to jedno żądanie Workera; pełny przebieg wszystkich wydziałów to setki–tysiące stron, a przebiegi są co 2 h, więc trzy
runnery mieszczą się w limicie. Worker nie jest otwartym proxy: token, tylko HTTPS, tylko dokładne hosty z listy, maksymalnie
trzy przekierowania i każde na liście, bez ciasteczek i bez `Authorization` wywołującego w stronę wydziału. Wyciekły token
unieważnisz nowym sekretem i aktualizacją runnerów.

WCY celowo nie ma na liście Workera: Incapsula odpowiada mu 403 również z Cloudflare, więc ten wydział zostaje na puli
(`EGRESS_FAIL_CLOSED`, wyżej). WLO, WML i WTC także dostają z zachodnich wyjść Workera 403 (AMS i FRA, 29.10.2026), więc
zostają z plebanią, gdy jej linia jest czysta. Northflank nie ma egressu, więc po ustawieniu
`PLANWAT_RELAY_URL`/`PLANWAT_RELAY_TOKEN` może brać WEL i WIG, ale jego `faculties` w `tools/refresh/fleet.json` obejmują
tylko IOE, WIG i WIM — WEL dzieli ścieżkę polityki z WLO, a te trzy działają także bez relaya.

Ten sam obraz chroni crawlery wolontariuszy (`tools/volunteer/compose.volunteer.yml`, publikowany jako
`ghcr.io/kilerdevs/planwat-crawler-egress`): crawler stoi w sieci bez trasy na zewnątrz, a proxy z `EGRESS_POOL=off` (i, dla
starszych obrazów, wszystkimi hostami wydziałów na liście `EGRESS_DIRECT_FACULTY`) działa jako zwykła lista dozwolonych hostów:
bezpośrednio GitHub (`github.com`, `api.github.com`, `codeload.github.com`, `*.githubusercontent.com`), magazyn artefaktów
GitHub Actions (`*.blob.core.windows.net`), PyPI (`pypi.org`, `*.pythonhosted.org`) i `*.wat.edu.pl`, reszta 403. Zob. [WOLONTARIUSZE.md](WOLONTARIUSZE.md#instalacja-ręczna).

## GUI monitoringu

Domyślnie tylko z maszyny: `compose.fragment.yml` wiąże port z `127.0.0.1:18080` (kontener `:8080`), więc z innego komputera
otwórz tunel `ssh -L 18080:127.0.0.1:18080 <host>` i wejdź na `http://localhost:18080/`. Żeby otworzyć panel w LAN, zwiąż adres
LAN (`"<ip-lan>:18080:8080"`) i najpierw ustaw `EGRESS_API_TOKEN`; panel poprosi wtedy o token. Runner rozmawia z GUI przez sieć
wewnętrzną, której ten bind nie dotyczy.
Panel jest zbudowany w stylu resztę serwisu (te same tokeny motywu, ciemny oraz jasny z przełącznikiem Auto / Ciemny / Jasny
zapisywanym w przeglądarce) i odświeża się bez przeładowania co 4 s z `GET /api/status`. Pokazuje:

- kartę „Odświeżanie planów”: pasek postępu, licznik sprawdzonych grup, tempo (grup/s), przewidywany koniec i wiersz na każdy
  wydział z jego stanem (w kolejce, sprawdza, czeka na odblokowanie, zablokowany, brak postępu, gotowe).
- kartę „Egress”: czas działania, obsłużone żądania proxy, tunele w toku i odmowy (liczniki od startu kontenera) oraz tryb puli
  (ROTATING, DIRECT albo FAIL-CLOSED, gdy host bez awaryjnego wyjścia nie ma zdrowego proxy);
- tabelę „Wydziały”: wiersz na host z trybem (ROTATING / DIRECT (lista) / DIRECT (bez puli) / DIRECT / FAIL-CLOSED), liczbą
  potwierdzonych wyjść i połączeń
  awaryjnych, z podpowiedziami w nagłówkach kolumn;
- kartę „Pula proxy”: rozmiar, zdrowych i odrzuconych wychodów oraz p95 opóźnienia (w sekundach), a w nagłówku mediana,
  liczniki nowych wychodów i obejść; w tabeli adres, stan, ping, „pudła” (nieudane próby per host) i źródło; wiersz ma podpowiedź z czasem
  ostatniego sprawdzenia, a nagłówek tabeli zostaje na miejscu przy przewijaniu;
- „Przebiegi odświeżania”: ostatnie 10 raportów z czasem trwania i liczbą sprawdzonych oraz pominiętych grup, kodem wyjścia
  (raport bez kodu czyta się jako „nieznany”), a każdy wydział ma podpowiedź ze sprawdzonymi/zmienionymi/pominiętymi, przyczyną
  (blokady albo nieudanego wylistowania) i czasem oczekiwania. Kliknięcie wiersza rozwija szczegóły przebiegu — profil, czasy, kod wyjścia i tabelę wydziałów
  (sprawdzone, zmiany, pominięte, stan, czas oczekiwania na odblokowanie, kiedy) — a rozwinięcie przeżywa kolejne odświeżenia panelu.
  Karta postępu pokazuje wynik ostatniego przebiegu i odlicza do następnego (cron `:23` co 2 h): w bezczynności „następny ≈ 16:23
  (za 1 h 59 min)”, w trakcie przebiegu „następny za X”. Raporty są też zapisywane w `/data/runs.json`. Na wąskich ekranach
  (poniżej 640 px) wiersze przebiegów układają się w bloki, szczegóły przewijają się poziomo, a tabele wydziałów i puli chowają
  najmniej istotne kolumny („obejścia”, „źródło”).

Znaczniki czasu raportów są w UTC bez strefy — panel czyta je jako UTC i pokazuje w czasie lokalnym.

Karta postępu jest zbudowana z grubych zdarzeń, które crawler wysyła najlepszym wysiłkiem na `POST /api/progress`
(`PLANWAT_EGRESS_PROGRESS`, domyślnie `http://<egress-ip>:8080/api/progress`, puste wyłącza; `run_start`, `faculty_start`,
przycinane `tick`, `faculty_done`, `wait_start`/`wait_end`, `run_done`). Egress stempluje każdą dostawę i liczy tempo każdego
wydziału z jego własnych `tick`ów (okno 180 s, przy zbyt krótkiej historii — mediana tempa całego przebiegu), a przewidywany
koniec to suma tego, co zostało w najwolniejszej ścieżce (pasach wydziałów) plus minuta na publikację kalendarzy. Wydział,
który czeka na odblokowanie albo zamilkł, pokazuje „wstrzymane” zamiast wymyślonej godziny — jeden zgubiony `tick` psuje
tylko dokładność, nigdy sensu, a przebieg bez zdarzeń przez 10 minut czyta się jako „bez wieści”. Stanu nie zapisuje się na
dysku: raport końcowy wciąż ląduje w `/data/runs.json`. Raport „rozpoczęty”, po którym nie przyszło zakończenie, znika z panelu
po 12 h, więc zawieszony przebieg nie udaje wiecznie trwającego.

Sprawdzenie stanu: `GET /api/status` (200 = GUI działa, także bez tokenu; dodaj jako `healthcheck:` w compose, a samo
„unhealthy” nigdy nie restartuje kontenera, więc połącz z mechanizmem w stylu autoheal).

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
   nietknięty jako wycofanie). GUI jest związane z `127.0.0.1`; jeśli ma być widoczne w LAN, zmień bind na adres LAN i ustaw
   w `.env` `EGRESS_API_TOKEN` — ten sam, który widzi krok odświeżania (crawler wysyła go w `Authorization` i `X-Token`). Akcja odświeżania nie ustawia go jawnie, żeby
   pusta wartość nie nadpisała tokenu odziedziczonego z otoczenia runnera.
3. (Opcjonalnie) Wdróż relay Cloudflare według [tools/egress/cloudflare/README.md](../tools/egress/cloudflare/README.md),
   wpisz `PLANWAT_RELAY_URL`/`PLANWAT_RELAY_TOKEN` do `.env` runnera oraz dokładny hostname Workera do
   `EGRESS_DIRECT_HOSTS` w `.env` egressu. Bez tego kroku egress działa jak dotąd.
4. `docker compose up -d --build egress`, otwórz `:18080` (tunel SSH albo adres LAN) i poczekaj na odświeżenie puli → ROTATING.
5. Przełączenie: `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy` runnera → `http://<egress-ip>:8888` z `NO_PROXY` obejmującym
   podsieć wewnętrzną (`localhost,127.0.0.1,<inner-subnet>`, żeby zapytania GUI i statusu omijały proxy),
   `docker compose up -d runner`.
6. Uruchom mały przebieg (`--faculty wcy --limit 5 --dry-run`) i obserwuj tryb w GUI oraz tabelę przebiegów. Z relayem
   sprawdź też jeden wydział z listy (np. `--faculty wtc --limit 2`).
7. Wycofanie (przy jakichkolwiek wątpliwościach): skieruj runner z powrotem na `http://<proxy-ip>:8888`, `up -d runner`.

Zmiana `allow.txt` nie jest potrzebna: pobieranie list i sprawdzanie dzieje się wewnątrz kontenera egress na jego własnej
bezpośredniej trasie, a ruch odświeżania wciąż płynie przez jedno proxy „dozwolone w duchu”, które egzekwuje tę samą politykę.

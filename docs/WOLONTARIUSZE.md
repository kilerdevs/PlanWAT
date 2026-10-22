<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Crawlery wolontariuszy

**Pomóż utrzymać plany aktualne: Twój crawler sprawdza część grup, a serwis przyjmuje tylko to, co da się zweryfikować.**

[![Collect](https://github.com/kilerdevs/PlanWAT/actions/workflows/collect.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/collect.yml)
![Dołączanie](https://img.shields.io/badge/do%C5%82%C4%85czanie-na%20zaproszenie-blue?style=flat)
![Kworum](https://img.shields.io/badge/kworum-2%20wolontariuszy-informational?style=flat)
![Sekrety projektu](https://img.shields.io/badge/sekrety%20projektu-brak-brightgreen?style=flat)

</div>

Plany odświeża dziś jedna maszyna na domowym łączu (zob. [REFRESH.md](REFRESH.md)). Gdy ona albo jej łącze leży,
albo wydział ją blokuje (WCY blokuje domowe łącze już teraz), strona się starzeje. Crawlery wolontariuszy to
zabezpieczenie: każdy sprawdza swoją część grup ze swojego łącza, a wyniki trafiają na stronę dopiero wtedy, gdy
zgadzają się z innymi albo pochodzą od osoby, której opiekun ufa w pełni.

Ten przewodnik prowadzi od zgłoszenia, przez uruchomienie i sprawdzenie, że działa, po rozwiązywanie problemów. Na
końcu jest część dla opiekuna projektu.

- [Jak to działa](#jak-to-działa)
- [Zanim zaczniesz](#zanim-zaczniesz)
- [Zgłoszenie](#zgłoszenie)
- [Token do forka](#token-do-forka)
- [Tryb A: Docker (zalecany)](#tryb-a-docker-zalecany)
- [Tryb B: runner na własnym forku](#tryb-b-runner-na-własnym-forku)
- [Co robi jeden przebieg](#co-robi-jeden-przebieg)
- [Co trafia do paczki](#co-trafia-do-paczki)
- [Jak sprawdzić, że działa](#jak-sprawdzić-że-działa)
- [Zasady crawlowania](#zasady-crawlowania)
- [Rozwiązywanie problemów](#rozwiązywanie-problemów)
- [Bezpieczeństwo](#bezpieczeństwo)
- [Dla opiekuna](#dla-opiekuna) (w tym [panel uprawnień](#panel-uprawnień))
- [Rezygnacja](#rezygnacja)

## Jak to działa

```
wolontariusz (Docker albo runner na forku)          projekt kilerdevs/PlanWAT
  czyta publiczną gałąź data i rejestr         ─┐
  refresh.py --assign: tylko swoja część grup    │
  bundle.py → <login>/PlanWAT, gałąź crawl ──────┼──► collect.yml (runner GitHub, co 30 min)
                                                 │      pobiera gałęzie crawl zarejestrowanych forków
domowy runner (refresh.yml, bez zmian) ──────────┼──►   sprawdza → waliduje → liczy głosy → push na data
                                                 │                                   └─► pages.yml
```

- **Nikt z zewnątrz nie pisze do repozytorium projektu.** Wolontariusz wypycha wyniki wyłącznie na gałąź `crawl`
  **własnego forka**, własnym tokenem, i nie dostaje żadnego sekretu projektu.
- **Koordynator** (`collect.yml`, `tools/volunteer/collect.py`) działa na runnerze GitHub, nigdy nie łączy się ze
  stronami wydziałów i niczego z forków nie uruchamia. Pobiera paczki jako dane i sprawdza je od zera.
- **Każde sprawdzenie grupy to głos** na konkretny plan (skrót `plan` kalendarza). Plan jest przyjmowany, gdy:
  - głosowała za nim osoba **zaufana** (`trusted`), albo
  - zgodziło się co najmniej **2 równorzędnych** (`peer`) w ciągu 12 godzin.
- **Przyjęte plany** trafiają na gałąź `data` z podpisem, kto je dostarczył (`volunteer-state.json`, pole `by`).

## Zanim zaczniesz

- Konto GitHub i fork [kilerdevs/PlanWAT](https://github.com/kilerdevs/PlanWAT) na tym koncie (nazwa dowolna,
  domyślnie `PlanWAT`).
- Maszyna, która działa przez większość doby: domowy serwer, Raspberry Pi 4 / 5, VPS, stary laptop. Wystarczy
  1 GB RAM i ok. 500 MB miejsca. Ruch: kilkadziesiąt MB co dwie godziny (głównie klon gałęzi `data`).
- Łącze, z którego strony wydziałów odpowiadają normalnie. Strony stoją za Incapsulą, która blokuje adresy centrów
  danych, więc **VPS-y często się nie nadają** — sprawdź to pierwszym przebiegiem próbnym (niżej). Jeśli Twoje
  łącze dociera tylko do części wydziałów, zgłoś tylko je (`faculties`).
- Docker z Compose v2 (tryb A) albo runner GitHub Actions, który potrafisz utwardzić (tryb B).
- Zgodny zegar systemowy (NTP). Paczki z czasem z przyszłości albo sprzed ponad 12 h są odrzucane.

## Zgłoszenie

Dołączanie jest na zaproszenie: o tym, kto zasila stronę, decyduje opiekun.

1. Otwórz zgłoszenie z szablonu [Volunteer crawler](https://github.com/kilerdevs/PlanWAT/issues/new?template=volunteer.yml):
   podaj swój fork (musi należeć do Twojego konta), tryb uruchomienia i wydziały, do których dociera Twoje łącze.
2. Opiekun dopisuje Cię do rejestru i ustawia poziom zaufania. Rejestr (`volunteers.json`) leży sam na gałęzi
   [`volunteers`](https://github.com/kilerdevs/PlanWAT/tree/volunteers) i zmienia go wyłącznie opiekun, podpisanym commitem.
3. Od najbliższego przebiegu (do 30 min) Twój login dostaje przydziały. Swój wpis zobaczysz na gałęzi `volunteers`.

**Poziomy zaufania:**

| `trust` | Znaczenie |
|---|---|
| `trusted` | Twój wynik jest przyjmowany sam, tak jak wynik domowego runnera. Dla osób, które opiekun zna. |
| `peer` | Twój wynik liczy się, gdy niezależnie potwierdzi go drugi wolontariusz `peer`. |
| `suspended` | Wpis zostaje, ale crawler nie dostaje przydziałów, a paczki są pomijane. |

## Token do forka

Crawler w trybie Docker wypycha paczkę tokenem, który ma dostęp **wyłącznie do Twojego forka**:

1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token.
2. Resource owner: Twoje konto. Expiration: np. 90 dni (ustaw przypomnienie o odnowieniu).
3. Repository access: **Only select repositories** → tylko Twój fork.
4. Permissions → Repository permissions → **Contents: Read and write**. Nic więcej.
5. Skopiuj token do `.env` (niżej). Nie wklejaj go nigdzie indziej.

W trybie B token nie jest potrzebny: workflow używa własnego `GITHUB_TOKEN` forka.

## Tryb A: Docker (zalecany)

Dwa kontenery: crawler w sieci wewnętrznej **bez trasy na zewnątrz** i proxy wyjściowe (to samo co na domowym
runnerze, [EGRESS.md](EGRESS.md)), które przepuszcza tylko GitHub i strony wydziałów, a wszystko inne odrzuca kodem 403.

### 1. Pliki

```sh
mkdir planwat-crawler && cd planwat-crawler
curl -fsSLO https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/compose.volunteer.yml
curl -fsSL -o .env https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/volunteer.env.example
mv compose.volunteer.yml compose.yml
chmod 600 .env
```

Uzupełnij `.env`: `PLANWAT_LOGIN` (Twój login z rejestru) i `PLANWAT_FORK_TOKEN`. `PLANWAT_FORK` ustaw tylko wtedy,
gdy fork nie nazywa się `PlanWAT`.

### 2. Sprawdź obraz

Obrazy są budowane przez workflow `crawler-image.yml` z tagu wydania i mają poświadczenie pochodzenia:

```sh
docker compose pull
gh attestation verify oci://ghcr.io/kilerdevs/planwat-crawler:latest --repo kilerdevs/PlanWAT
gh attestation verify oci://ghcr.io/kilerdevs/planwat-crawler-egress:latest --repo kilerdevs/PlanWAT
```

Możesz przypiąć konkretne wydanie: `PLANWAT_VERSION=1.2.0` w `.env` (wtedy aktualizujesz świadomie).

### 3. Przebieg próbny

Jeden przebieg, który pobiera i konwertuje, ale niczego nie zapisuje ani nie wypycha:

```sh
docker compose up -d egress
docker compose run --rm -e PLANWAT_ONCE=1 -e PLANWAT_DRY_RUN=1 crawler
```

W logu zobaczysz `volunteer <login> (peer), window …` i dla każdego wydziału, ile grup ma do sprawdzenia. Linie
`BLOCKED` oznaczają, że wydział blokuje Twoje łącze — usuń go ze swoich `faculties` w rejestrze.
Panel proxy: <http://localhost:18080/> (postęp przebiegu, wydziały, odmowy).

### 4. Start

```sh
docker compose up -d
docker compose logs -f crawler
```

Crawler robi przebieg od razu, a potem co 2 godziny (z losowym przesunięciem do 20 min).

### 5. Aktualizacje

```sh
docker compose pull && docker compose up -d
```

Koordynator odrzuca paczki ze zbyt starej wersji crawlera (`min_version` w rejestrze), więc aktualizuj po każdym
wydaniu. Watchtower albo cron z powyższą komendą też się nada.

### Utwardzenie (już w `compose.yml`)

Crawler działa jako użytkownik bez uprawnień, z systemem plików tylko do odczytu, bez żadnych capabilities, z
`no-new-privileges`, limitami pamięci i procesów i bez otwartych portów. Jedyne, co słucha na hoście, to panel proxy
na `127.0.0.1:18080`. Dane robocze leżą w wolumenie `work` i są odtwarzane w każdym przebiegu.

## Tryb B: runner na własnym forku

Dla osób, które już utrzymują runnery GitHub Actions. Używa tej samej akcji co domowy runner projektu.

1. W forku: Settings → Actions → General → zezwól na Actions. Zakładka Actions → włącz workflowy (GitHub wyłącza
   harmonogramy w świeżych forkach).
2. Settings → Actions → Runners → New self-hosted runner. Zarejestruj go z etykietą **`planwat-volunteer`**.
3. Utwardź runner tak jak domowy runner projektu ([REFRESH.md](REFRESH.md#własny-runner-jedyny)):
   - kontener, użytkownik bez uprawnień, bez montowań hosta i bez gniazda Dockera;
   - runner efemeryczny (jedno zadanie) albo czyszczony katalog roboczy;
   - ruch wychodzący tylko do GitHub i `*.wat.edu.pl` — najprościej przez proxy z [EGRESS.md](EGRESS.md).
4. Workflow `Volunteer crawl` (`.github/workflows/volunteer.yml`) uruchamia się co 2 godziny (`:41`) i tylko w
   forkach. Pierwszy raz uruchom go ręcznie: Actions → Volunteer crawl → Run workflow.
5. Trzymaj fork aktualny (Sync fork na stronie forka), bo koordynator odrzuca stare wersje crawlera.

Rejestr (gałąź `volunteers`) i dane są zawsze czytane z projektu, nigdy z Twojego forka.

## Co robi jeden przebieg

1. Klonuje publiczną gałąź `data` projektu (ostatnie przyjęte kalendarze i stan sprawdzeń) i pobiera
   rejestr `volunteers.json` z gałęzi `volunteers`.
2. Wylicza swój **przydział** (`tools/volunteer/assign.py`). Dla każdej grupy i dwugodzinnego okna wszyscy liczą to
   samo haszowanie (rendezvous) po aktywnych wolontariuszach danego wydziału:
   - jeśli najwyżej w rankingu jest osoba zaufana, grupę sprawdza tylko ona;
   - w przeciwnym razie sprawdza ją dwóch najwyżej ocenionych `peer`ów;
   - pary zmieniają się co okno, więc nikt nie ma stałego partnera.
   
   Dzięki temu strona wydziału dostaje około dwóch zapytań na grupę na okno, niezależnie od liczby wolontariuszy.
3. Pomija grupy sprawdzone niedawno (przez kogokolwiek, komu serwis ufa) — jak domowy runner.
4. Pobiera strony w tempie wolontariusza (4–9 s przerwy, jedno zapytanie naraz na wydział, `robots.txt`,
   rewalidacja warunkowa `304`), konwertuje i waliduje tymi samymi funkcjami co domowy runner.
5. `bundle.py` składa paczkę i wypycha ją na gałąź `crawl` forka jako jeden commit bez historii (`--force`).

## Co trafia do paczki

```
manifest.json
timetables/2026-27-zima/WCY26KY3S1.ics      tylko kalendarze, które się zmieniły
```

```json
{"format": 1, "version": "1.2.0", "login": "twoj-login", "seq": 1792000000,
 "started": "2026-10-20T10:00:00", "ended": "2026-10-20T10:40:00", "window": 14933,
 "groups": {"WCY26KY3S1@2026-27-zima": {"status": "changed", "plan": "<sha256>", "at": "2026-10-20T10:12:31"}},
 "faculties": {"wcy": {"blocked": false, "cause": null}}}
```

- `status`: `changed` (nowy plan), `unchanged` (taki jak opublikowany), `not_ready` (wydział pokazuje jeszcze inny
  semestr), `gone` (404). Dwa ostatnie są informacyjne i nie są głosami.
- `plan`: SHA-256 kalendarza bez linii zmiennych (`DTSTAMP`, `X-PLAN-GENERATED`, `X-PLAN-UPDATED`), więc dwie
  osoby, które widziały ten sam plan, zgadzają się co do bajtu.

**Prywatność:** paczka nigdy nie zawiera surowych stron wydziałów (są na nich nazwiska prowadzących, a fork jest
publiczny), tylko skonwertowane kalendarze, w których nazwisk nie ma (`build.load_term` odrzuca każdy kalendarz z
`CONTACT` albo `Prowadzący:`). Publiczne są: Twój login, czasy przebiegów i to, które grupy sprawdziłeś.

## Jak sprawdzić, że działa

1. **Twój fork**, gałąź `crawl`: świeży commit „PlanWAT volunteer crawl” i `manifest.json` z bieżącą godziną.
2. **Przebiegi koordynatora** (publiczne): [Actions → Collect volunteer crawls](https://github.com/kilerdevs/PlanWAT/actions/workflows/collect.yml).
   W logu jest linia o Twojej paczce:
   - `twoj-login: 37 votes, 0 calendars rejected (crawler 1.2.0)` — wszystko w porządku;
   - `twoj-login: bundle refused: …` — zob. [Rozwiązywanie problemów](#rozwiązywanie-problemów).
3. **Gałąź `data`**, plik `volunteer-state.json`: grupy, które przyjęto z Twoim udziałem, mają Twój login w `by`.
4. **Strona grupy**: „Sprawdzono” pokazuje czas ostatniego przyjętego sprawdzenia, także Twojego.

Jako `peer` pierwsze przyjęte wyniki zobaczysz dopiero, gdy ktoś inny sprawdzi te same grupy — przy niewielu
wolontariuszach może to chwilę potrwać.

## Zasady crawlowania

Strony wydziałów to cudza infrastruktura, a blokada uderza w każdego, kto korzysta z tego samego łącza. Dlatego:

- **Uruchamiaj opublikowany obraz albo workflow projektu bez zmian.** Nie skracaj przerw, nie zwiększaj równoległości,
  nie sprawdzaj grup spoza przydziału. Za szybki crawl zostanie zablokowany przez Incapsulę na godziny.
- **Jedna instancja na login.** Dwie instancje to podwójny ruch i paczki nadpisujące się nawzajem.
- **Blokada to sygnał, by przestać.** Crawler sam odczekuje blokadę (wyuczonym czasem) i zgłasza ją proxy. Nie
  restartuj go w kółko. Jeśli wydział blokuje Cię stale, poproś o usunięcie go z Twoich `faculties`.
- **Nie omijaj zabezpieczeń stron** (CAPTCHA, logowanie, ukryte adresy). Crawler czyta tylko publiczne strony planów,
  respektuje `robots.txt` i tak ma zostać.
- **Nie publikuj surowych stron** ani niczego, co zawiera nazwiska kadry — także w issue i w logach.

## Rozwiązywanie problemów

| Objaw | Przyczyna | Co zrobić |
|---|---|---|
| `<login> is not an active volunteer`, kod 2 | Brak w rejestrze albo poziom „wstrzymany” | Sprawdź swój wpis na gałęzi `volunteers` i pisownię loginu |
| `volunteer … : nothing` | Twoje `faculties` nie pokrywają się z włączonymi wydziałami | Popraw `faculties` w rejestrze |
| Przebieg nie sprawdza żadnej grupy | Za mało `peer`ów dla Twoich wydziałów (potrzeba dwóch) albo wszystkie grupy są świeże | To normalne; przydziały pojawią się, gdy dołączy ktoś drugi |
| `push to … failed` | Token wygasł, nie obejmuje forka albo nie ma Contents: write | Wygeneruj token od nowa (sekcja Token) |
| `bundle refused: crawler X is older than Y` | Stara wersja | `docker compose pull && docker compose up -d` / Sync fork |
| `bundle refused: replayed or out of order` | Zegar cofnął się albo wypchnięto starą paczkę | Włącz NTP; następny przebieg naprawi to sam |
| `bundle refused: stale` / `bad end time` | Zegar źle ustawiony albo paczka czekała ponad 12 h | Włącz NTP |
| `bundle refused: not a plain file` / `not a manifest or a calendar path` | Na gałęzi `crawl` jest coś poza paczką | Nie commituj ręcznie na `crawl`; następny przebieg nadpisze gałąź |
| `<grupa> rejected (lost too many events …)` | Strona wydziału była chwilowo niepełna | Nic; inni (albo kolejny przebieg) potwierdzą właściwy plan |
| `BLOCKED` w logu crawlera | Incapsula blokuje Twoje łącze | Odczekaj; przy stałej blokadzie zrezygnuj z tego wydziału |
| Issue „Wolontariusz `<login>` niezgodny” | Trzy razy w tygodniu Twoje głosy przegrały z planem przyjętym przez innych | Sprawdź wersję i log; opiekun przywraca po wyjaśnieniu |
| Panel `localhost:18080` nie działa | Kontener `egress` nie wystartował | `docker compose logs egress` |

## Bezpieczeństwo

### Dla Ciebie

- Obraz jest budowany publicznie z tagu wydania i ma poświadczenie pochodzenia (`gh attestation verify`).
- Nie dostajesz żadnego sekretu projektu. Twój token działa tylko na Twój fork, tylko na zawartość.
- Crawler nie ma trasy na zewnątrz poza proxy, które wpuszcza wyłącznie GitHub i `*.wat.edu.pl`, i nie otwiera
  żadnego portu przychodzącego.
- Paczki są publiczne i podpisane Twoim loginem — to, co wysyłasz, widać i da się to audytować.

### Dla serwisu

- **Pojedynczy `peer` niczego nie opublikuje.** Zmowa wymaga dwóch kont zatwierdzonych przez opiekuna, a pary
  zmieniają się co dwie godziny.
- **Każdy kalendarz przechodzi pełną walidację serwisu.** Musi:
  - zbudować się w `build.load_term`;
  - nosić własny kod grupy i nie stracić ponad 40% zajęć;
  - mieścić się w semestrze i nie zawierać nazwisk kadry.

  Strony są escapowane i chronione CSP przypiętym hashami, więc najgorszy możliwy skutek to błędne godziny zajęć, z
  podpisem, kto je dostarczył, i do cofnięcia jednym poleceniem.
- **Głos „bez zmian” nigdy nie blokuje zmiany**, którą potwierdziło kworum, więc nie da się zamrozić planu fałszywym
  „nic się nie zmieniło”.
- **Koordynator nie wykonuje niczego z forków.** Czyta bloby gitem bez checkoutu, z limitami rozmiaru i listą
  dozwolonych ścieżek, a jego token nie może uruchamiać workflowów ani zmieniać `master`.
- **Czego to nie rozwiązuje:** wolontariusz nie może *udowodnić*, że strona pochodzi z WAT. Wymagałoby to
  notaryzacji TLS, a to tutaj przesada. Obroną jest kworum, tożsamość z rejestru i rozliczalność.

Szczegóły modelu zagrożeń: [SECURITY.md](../SECURITY.md).

## Dla opiekuna

### Panel uprawnień

Uprawnienia zmieniasz w przeglądarce, w panelu uruchamianym z własnego klonu repozytorium:

```sh
python3 tools/volunteer/manage.py
```

Otwiera się strona (adres z jednorazowym tokenem jest też w terminalu), na której:

- widzisz każdego wolontariusza z jego stanem u koordynatora: ostatnią paczkę, liczbę przyjętych kalendarzy,
  niezgodności w tym tygodniu i to, czy został odsunięty;
- przełączasz poziom: **Zaufany / Równorzędny / Wstrzymany**, i wybierasz wydziały (albo „Wszystkie”);
- dodajesz osobę (login i fork) albo ją usuwasz;
- zmieniasz zasady głosowania: kworum, ważność głosu, najstarszą wersję crawlera;
- przywracasz odsuniętego wolontariusza jednym kliknięciem (uruchamia `collect.yml` z `unbench`; potrzebny `gh`).

Pasek na dole pokazuje, co się zmieni. **Zapisz i opublikuj** robi jeden commit z samym `volunteers.json`,
**podpisany Twoim kluczem** (ten sam co dla `master`), i wypycha go na gałąź `volunteers`. Zmiana działa od
najbliższego przebiegu koordynatora, czyli najpóźniej po 30 minutach, bez wydania i bez PR. Pierwszy zapis tworzy
gałąź. Jeśli w międzyczasie ktoś zmienił rejestr, panel odmówi zapisu i poprosi o odświeżenie.

Panel słucha tylko na `127.0.0.1`, wymaga tokenu z adresu i odrzuca żądania z innym nagłówkiem `Host`.

**Dlaczego to bezpieczne bez PR:** koordynator bierze rejestr tylko z commita, który GitHub weryfikuje jako podpisany
przez osobę z listy `REGISTRY_EDITORS` w `collect.yml`. Ta lista leży na chronionym `master`, więc token, który może
wypychać gałęzie (domowego runnera albo samego koordynatora), nie nada nikomu zaufania. Inny commit na gałęzi
`volunteers` zatrzymuje koordynatora z błędem, zamiast zostać użyty. Dla porządku chroń też samą gałąź (Settings →
Rules → New branch ruleset, cel `volunteers`: ogranicz aktualizacje do siebie, zablokuj force push i usuwanie,
wymagaj podpisanych commitów).

### Pozostałe przełączniki

- **Przyjęcie wolontariusza:** po zgłoszeniu dopisz go w panelu (domyślnie jako równorzędnego). `CODEOWNERS` wymaga
  Twojej recenzji dla całego kodu crawlowania.
- **Włączenie publikowania:** dopóki zmienna repozytorium `PLANWAT_COLLECT_LIVE` nie ma wartości `true`, każdy
  przebieg `collect.yml` jest próbny: loguje, co by przyjął, i niczego nie zapisuje. Settings → Secrets and
  variables → Actions → Variables.
- **Ustawienia rejestru** (w panelu, sekcja „Zasady głosowania”):
  - `quorum` (2–5) — ilu `peer`ów musi się zgodzić;
  - `window_hours` (2–48) — jak długo głosy są ważne;
  - `min_version` — najstarsza przyjmowana wersja crawlera. Podnieś ją po wydaniu, które zmienia konwersję.
- **Cofnięcie wyników wolontariusza:** Actions → Collect volunteer crawls → Run workflow z `revert = <login>` i
  `since = 2026-10-20T00:00:00` (UTC). Każdy kalendarz przyjęty z jego udziałem od tej chwili wraca do poprzedniej
  wersji, a grupy są sprawdzane od nowa. Lokalnie:
  `python tools/volunteer/collect.py --registry <volunteers.json> --data <klon data> --revert <login> --since <iso>`.
- **Odsunięcie:**
  - automatyczne: 3 przegrane głosy w 7 dni → głosy przestają się liczyć i otwiera się issue;
  - przywrócenie: przycisk „Przywróć” w panelu (albo Run workflow z `unbench = <login>`);
  - trwale: „Wstrzymany” w panelu.
- **Domowy runner** działa jak dotąd i jest zaufaną kotwicą: jego wyniki idą prosto na `data`. Grupy niedawno
  potwierdzone przez wolontariuszy pomija, bo `core.State` uwzględnia przyjęte stemple z `volunteer-state.json`.
- **Konflikty:** domowy runner i koordynator piszą różne pliki stanu. Jeśli w tej samej chwili zmienią ten sam
  kalendarz, koordynator ustępuje i liczy głosy ponownie w następnym przebiegu.

## Rezygnacja

1. `docker compose down -v` (albo wyrejestruj runner i wyłącz workflow w forku).
2. Usuń token (Settings → Developer settings → Fine-grained tokens → Delete).
3. Usuń gałąź `crawl` z forka, jeśli chcesz.
4. Napisz w swoim zgłoszeniu — opiekun usunie Cię z rejestru.

Dziękujemy!

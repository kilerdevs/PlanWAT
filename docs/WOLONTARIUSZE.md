<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Crawlery wolontariuszy

**Pomóż utrzymać plany aktualne: Twój crawler sprawdza część grup, a serwis przyjmuje tylko to, co da się zweryfikować.**

[![Instalator](https://github.com/kilerdevs/PlanWAT/actions/workflows/installer.yml/badge.svg?branch=dev)](https://github.com/kilerdevs/PlanWAT/actions/workflows/installer.yml)
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
- [Szybki start](#szybki-start) (jedno polecenie na Linux, macOS i Windows)
- [Zgłoszenie](#zgłoszenie)
- [Polecenie planwat-crawler](#polecenie-planwat-crawler)
- [Aktualizacje](#aktualizacje)
- [Instalacja ręczna](#instalacja-ręczna)
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

- Konto GitHub. Fork [kilerdevs/PlanWAT](https://github.com/kilerdevs/PlanWAT) instalator pomoże utworzyć jednym
  kliknięciem.
- Maszyna, która działa przez większość doby: domowy serwer, Raspberry Pi 4 / 5 (system **64-bitowy**), VPS, stary
  laptop, komputer z Windows albo macOS. Wystarczy 1 GB RAM i ok. 1 GB miejsca. Ruch: kilka MB co dwie godziny
  (dane projektu są pobierane przyrostowo).
- Łącze, z którego strony wydziałów odpowiadają normalnie. Strony stoją za Incapsulą, która blokuje adresy centrów
  danych, więc **VPS-y często się nie nadają**. Instalator sprawdza to sam: wysyła po jednym zapytaniu do każdego
  wydziału i mówi, które Cię wpuszczają.
- Zegar nie musi być idealny: crawler mierzy, o ile Twój zegar odbiega od GitHuba, i poprawia znaczniki czasu. Przy
  odchyłce ponad 2 minuty poprosi o włączenie NTP.

## Szybki start

Instalator robi wszystko po kolei i przed jakąkolwiek zmianą pokazuje plan:

1. instaluje, czego brakuje: Docker z Compose (z oficjalnych, podpisanych repozytoriów Dockera; na macOS Colima, na
   Windows Docker Desktop) i GitHub CLI (tylko do weryfikacji obrazów);
2. pyta o login i token do Twojego forka (linki są wypełnione, wystarczy kliknąć);
3. pobiera obrazy crawlera i **sprawdza ich pochodzenie** (`gh attestation verify`: zbudowane przez
   `crawler-image.yml` w kilerdevs/PlanWAT, nic innego), zanim cokolwiek w nich uruchomi, i przypina je skrótem;
4. uruchamia kreatora: fork, token, które wydziały odpowiadają z Twojego łącza, czy jesteś w rejestrze (jeśli nie,
   daje gotowe, wypełnione zgłoszenie), automatyczne aktualizacje;
5. startuje crawler i ustawia codzienną, zweryfikowaną aktualizację (możesz z niej zrezygnować).

Instalator nigdy nie dopisuje Cię do grupy `docker` (to uprawnienia roota pod inną nazwą); tam, gdzie musi, pyta o `sudo`.
Można go uruchomić ponownie w każdej chwili: naprawi, czego brakuje.

**Linux** (Debian, Ubuntu, Raspberry Pi OS 64-bit, Mint, Fedora, RHEL / CentOS / Rocky / Alma, Arch, openSUSE, WSL2)
**i macOS** (potrzebny [Homebrew](https://brew.sh)):

```sh
curl -fsSLO https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/install.sh
less install.sh     # przeczytaj, zanim uruchomisz
sh install.sh
```

**Windows 10 / 11** (PowerShell; Docker Desktop przy pierwszej instalacji może poprosić o restart, wtedy uruchom
skrypt jeszcze raz, a dokończy od miejsca, w którym przerwał):

```powershell
irm https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/install.ps1 -OutFile planwat-install.ps1
notepad planwat-install.ps1     # przeczytaj, zanim uruchomisz
powershell -ExecutionPolicy Bypass -File .\planwat-install.ps1
```

`sh install.sh --check` (Windows: `-Check`) pokazuje tylko, co zostałoby zainstalowane, i niczego nie zmienia.

**Kanały.** Domyślnie (`stable`) instalator bierze najnowsze wydanie: pliki z jego tagu i obrazy `:<wersja>`. Kanał
`dev` bierze to, co jest na gałęzi `dev`: pliki z tej gałęzi i obrazy `:dev`, które `crawler-image.yml` publikuje (z tym
samym poświadczeniem pochodzenia) po każdej zmianie crawlera na `dev`. Kanał zapamiętuje `.env`, więc aktualizacje idą
za nim; na `dev` aktualizacja następuje, gdy zmieni się zweryfikowany obraz.

```sh
curl -fsSLO https://raw.githubusercontent.com/kilerdevs/PlanWAT/dev/tools/volunteer/install.sh
sh install.sh --channel dev              # Windows: .\planwat-install.ps1 -Channel dev
planwat-crawler update --channel stable  # powrót na wydania (Windows: planwat-crawler update -Channel stable)
```

Dopóki żadne wydanie nie zawiera crawlera wolontariusza, kanał `stable` mówi to wprost i odsyła do `--channel dev`.

**Token.** Crawler wypycha paczki tokenem fine-grained, który powinien widzieć **wyłącznie Twój fork** (Contents: Read
and write, nic więcej). Instalator otwiera wypełniony formularz; Ty wybierasz tylko repozytorium (swój fork) i klikasz
Generate. Token klasyczny (`ghp_…`) albo token `gh auth login` (`gho_…`) jest odrzucany: sięga do wszystkich Twoich
repozytoriów. Crawler sprawdza, że token może pisać do forka, ale nie sprawdzi, czy nie obejmuje też innych
repozytoriów, więc w formularzu zostaw „Only select repositories” z samym forkiem.
Token służy też do weryfikacji obrazów, dlatego instalator pyta o niego przed uruchomieniem czegokolwiek z obrazu.
Gdy zbliża się jego wygaśnięcie (14 dni), crawler, `planwat-crawler doctor` i panel opiekuna to pokażą; nowy wklejasz
przez `planwat-crawler setup`.

## Zgłoszenie

Dołączanie jest na zaproszenie: o tym, kto zasila stronę, decyduje opiekun.

1. Kreator sprawdza, czy jesteś w rejestrze. Jeśli nie, wypisuje link do wypełnionego zgłoszenia (szablon
   [Volunteer crawler](https://github.com/kilerdevs/PlanWAT/issues/new?template=volunteer.yml)) z Twoim forkiem i
   wydziałami, które odpowiadają z Twojego łącza. Sprawdź je i kliknij Submit.
2. Opiekun dopisuje Cię do rejestru i ustawia poziom zaufania. Rejestr (`volunteers.json`) leży sam na gałęzi
   [`volunteers`](https://github.com/kilerdevs/PlanWAT/tree/volunteers) i zmienia go wyłącznie opiekun, podpisanym
   commitem. Crawler (tak samo jak koordynator) czyta go tylko z commita, który GitHub weryfikuje jako podpisany przez
   opiekuna.
3. Crawler może działać już wcześniej: czeka uprzejmie (co 30 minut zagląda do rejestru) i sam zaczyna, gdy pojawi się
   Twój wpis.

**Poziomy zaufania:**

| `trust` | Znaczenie |
|---|---|
| `trusted` | Twój wynik jest przyjmowany sam, tak jak wynik domowego runnera. Dla osób, które opiekun zna. |
| `peer` | Twój wynik liczy się, gdy niezależnie potwierdzi go drugi wolontariusz `peer`. |
| `suspended` | Wpis zostaje, ale crawler nie dostaje przydziałów, a paczki są pomijane. |

## Polecenie planwat-crawler

Instalator zostawia polecenie `planwat-crawler` (Linux / macOS: `~/.local/bin`, Windows: w `PATH` użytkownika):

| Polecenie | Co robi |
|---|---|
| `planwat-crawler status` | co crawler robi teraz, kiedy następny przebieg i co koordynator powiedział o ostatniej paczce |
| `planwat-crawler logs` / `logs egress` | dziennik crawlera / proxy wyjściowego na żywo |
| `planwat-crawler doctor` | pełna diagnostyka: zegar, rejestr, wersja, token, fork, proxy, wydziały, werdykt koordynatora; przy każdym problemie podpowiedź, co zrobić |
| `planwat-crawler setup` | kreator od nowa (np. nowy token) |
| `planwat-crawler update` | aktualizacja teraz (zweryfikowana, z wycofaniem) |
| `planwat-crawler autoupdate on` / `off` | włącza / wyłącza codzienne aktualizacje |
| `planwat-crawler start` / `stop` / `restart` | uruchamia / zatrzymuje crawler |
| `planwat-crawler uninstall` | usuwa crawler, jego dane i harmonogram (tylko po wyraźnym „t”; bez pytania: `--yes`) |

`status` i `doctor` przy zatrzymanym crawlerze mówią to wprost i pokazują ostatni zapisany stan; `doctor` zgłasza też
crawler, który od ponad 3 godzin nie zapisał stanu (nie działa albo się zawiesił).

Panel proxy z postępem przebiegu: <http://localhost:18080/>.

## Aktualizacje

Domyślnie raz dziennie (systemd albo cron na Linuksie, launchd na macOS, Harmonogram zadań na Windows) crawler:

1. sprawdza najnowsze wydanie projektu;
2. pobiera jego obrazy i weryfikuje ich pochodzenie tak samo jak instalator;
3. przypina nowe skróty, uruchamia nową wersję i po półtorej minuty sprawdza, że oba kontenery działają, nie
   restartowały się i nie są oznaczone jako niezdrowe;
4. jeśli nie wystartowały albo nie przeszły tego sprawdzenia, **wraca do poprzedniej wersji**.

Gdy Docker (albo Colima) nie działa, aktualizacja najpierw go uruchamia. Każdy błąd (np. obraz bez poświadczenia)
zostawia działającą wersję bez zmian. Log: `update.log` w katalogu crawlera (na każdym systemie, także z systemd).

Z automatycznych aktualizacji możesz zrezygnować: `planwat-crawler autoupdate off` (albo w kreatorze). Wtedy crawler
zgłasza w logu i w `doctor`, że jest nowsza wersja, a aktualizujesz sam przez `planwat-crawler update`. Pamiętaj, że
koordynator odrzuca paczki ze zbyt starej wersji (`min_version` w rejestrze); taki crawler w ogóle nie crawluje, tylko
prosi o aktualizację, żeby nie obciążać stron wydziałów na darmo.

## Instalacja ręczna

Dla osób, które wolą zrobić wszystko same (potrzebny Docker z Compose ≥ 2.24 i `gh` ≥ 2.49):

```sh
mkdir planwat-crawler && cd planwat-crawler
curl -fsSL -o compose.yml https://raw.githubusercontent.com/kilerdevs/PlanWAT/master/tools/volunteer/compose.volunteer.yml
# obrazy: sprawdź pochodzenie i przypnij skróty w .env
for name in planwat-crawler planwat-crawler-egress; do
  docker pull -q ghcr.io/kilerdevs/$name:latest
  GH_TOKEN=<twój token> gh attestation verify oci://ghcr.io/kilerdevs/$name:latest --repo kilerdevs/PlanWAT \
    --signer-workflow kilerdevs/PlanWAT/.github/workflows/crawler-image.yml
done
docker compose run --rm --user "$(id -u):$(id -g)" -v "$PWD:/config" crawler setup   # kreator zapisuje .env
docker compose up -d
```

Przypięcie skrótów: w `.env` wpisz `PLANWAT_CRAWLER_IMAGE=ghcr.io/kilerdevs/planwat-crawler@sha256:…` i
`PLANWAT_EGRESS_IMAGE=…` (skróty z `docker image inspect --format '{{index .RepoDigests 0}}' <obraz>`).

**Utwardzenie (już w `compose.yml`):** crawler działa jako użytkownik bez uprawnień, z systemem plików tylko do
odczytu, bez żadnych capabilities, z `no-new-privileges`, limitami pamięci i procesów, bez otwartych portów i bez trasy
na zewnątrz poza proxy, które przepuszcza tylko GitHub (z jego magazynem plików), PyPI i strony wydziałów. Jedyne, co
słucha na hoście, to panel proxy na `127.0.0.1:18080`. Obie usługi mają healthcheck, a `init: true` pozwala zatrzymać crawler czysto.

## Tryb B: runner na własnym forku

Dla osób, które już utrzymują runnery GitHub Actions. Używa tej samej akcji co domowy runner projektu.

1. W forku: Settings → Actions → General → zezwól na Actions. Zakładka Actions → włącz workflowy (GitHub wyłącza
   harmonogramy w świeżych forkach).
2. Settings → Actions → Runners → New self-hosted runner. Zarejestruj go z etykietą **`planwat-volunteer`**.
3. Utwardź runner tak jak domowy runner projektu ([REFRESH.md](REFRESH.md#własny-runner-jedyny)):
   - kontener, użytkownik bez uprawnień, bez montowań hosta i bez gniazda Dockera;
   - runner efemeryczny (jedno zadanie) albo czyszczony katalog roboczy;
   - ruch wychodzący tylko do GitHub, PyPI (`pypi.org`, `files.pythonhosted.org`: akcja instaluje przy każdym
     przebiegu `curl_cffi` i `pymupdf`) i `*.wat.edu.pl` — najprościej przez proxy z [EGRESS.md](EGRESS.md).
4. Workflow `Volunteer crawl` (`.github/workflows/volunteer.yml`) uruchamia się co 2 godziny, 20 minut po otwarciu
   okna (`:20` UTC), kończy najpóźniej po 75 minutach (przed następnym oknem) i działa tylko w forkach. Pierwszy raz
   uruchom go ręcznie: Actions → Volunteer crawl → Run workflow.
5. Trzymaj fork aktualny (Sync fork na stronie forka), bo koordynator odrzuca stare wersje crawlera.

Rejestr (gałąź `volunteers`, tylko z commita podpisanego przez opiekuna) i dane są zawsze czytane z projektu, nigdy
z Twojego forka. Wyuczone tempo i czasy blokad Twojego łącza runner trzyma w swoim katalogu narzędzi między przebiegami.

## Co robi jeden przebieg

Przebiegi idą za dwugodzinnymi oknami przydziałów: jeden na okno, 5–35 minut po jego otwarciu. Dzięki temu osoby,
które sprawdzają te same grupy, robią to w tym samym oknie, a strona wydziału nie dostaje dwóch zapytań o jedno okno.
Przebieg robi tylko to, co może skończyć się przyjętą paczką, a gdy staje wcześniej, mówi dlaczego:

1. **Zegar.** Mierzy odchyłkę od GitHuba; ponad 30 s poprawia (paczki nie są odrzucane jako „stare” albo „z
   przyszłości”), ponad 2 minuty dodatkowo zgłasza.
2. **Rejestr.** Pobiera `volunteers.json` z gałęzi `volunteers`, tylko z commita zweryfikowanego jako podpisany przez
   opiekuna. Brak wpisu, „wstrzymany” albo zbyt stara wersja crawlera: bez crawlowania, ponowna próba za 30 minut.
3. **Dane.** Dociąga przyrostowo publiczną gałąź `data` projektu (ostatnie przyjęte kalendarze, stan sprawdzeń i
   werdykty koordynatora) do tego samego klonu. Przebieg przerwany w połowie (restart kontenera, awaria) wznawia się
   w tym samym oknie na tym samym klonie, bez dociągania: grup sprawdzonych przed przerwą (stan zapisuje się co 25
   sprawdzeń) nie pyta drugi raz.
4. **Werdykt.** Wypisuje, co koordynator powiedział o poprzedniej paczce (przeczytana, ile głosów, ile przyjęto,
   albo dlaczego odrzucona). Odsunięty przez koordynatora: bez crawlowania, dopóki opiekun nie przywróci.
5. **Przydział** (`tools/volunteer/assign.py`). Dla każdej grupy i okna wszyscy liczą to samo haszowanie (rendezvous)
   po wolontariuszach danego wydziału, którzy **naprawdę działają**: pomija tych, od których koordynator nie dostał
   paczki od 6 godzin (nowa osoba ma dobę od dopisania), i tych, których łącze ten wydział niedawno blokował. Potem:
   - jeśli najwyżej w rankingu jest osoba zaufana, grupę sprawdza tylko ona;
   - w przeciwnym razie sprawdza ją dwóch najwyżej ocenionych `peer`ów;
   - pary zmieniają się co okno, więc nikt nie ma stałego partnera.

   Strona wydziału dostaje więc około dwóch zapytań na grupę na okno, niezależnie od liczby wolontariuszy, a grupy
   osoby, która wyłączyła komputer albo trafiła na blokadę, same przechodzą do innych.
6. **Crawl.** Pomija grupy sprawdzone niedawno (przez kogokolwiek, komu serwis ufa), najpierw bierze najdawniej
   sprawdzone. Pobiera strony w tempie wolontariusza (4–9 s przerwy, jedno zapytanie naraz na wydział, `robots.txt`,
   rewalidacja warunkowa `304`), z tempem i czasami blokad wyuczonymi dla **Twojego** łącza (trzyma je między
   przebiegami), konwertuje i waliduje tymi samymi funkcjami co domowy runner.
7. **Paczka.** `bundle.py` sprawdza token (dostęp do forka, nie klasyczny, data wygaśnięcia), składa paczkę i
   wypycha ją na gałąź `crawl` forka jako jeden commit bez historii (`--force`, z ponowieniem). Okno bez grup do
   sprawdzenia też wysyła (pustą) paczkę: koordynator wie wtedy, że Twój crawler żyje. Paczka, która nie dotarła do
   forka (token, fork, sieć, wypychanie bez odpowiedzi przez 5 minut), kończy przebieg jako nieudany, a `status` i
   `doctor` podają powód; tego okna crawler nie sprawdza drugi raz, następne wyśle nową paczkę.

## Co trafia do paczki

```
manifest.json
timetables/2026-27-zima/WCY26KY3S1.ics      tylko kalendarze, które się zmieniły
```

```json
{"format": 1, "version": "1.2.0", "login": "twoj-login", "seq": 1792000000,
 "started": "2026-10-20T10:00:00", "ended": "2026-10-20T10:40:00", "window": 14933,
 "token_expires": "2027-01-18T10:00:00",
 "groups": {"WCY26KY3S1@2026-27-zima": {"status": "changed", "plan": "<sha256>", "at": "2026-10-20T10:12:31"}},
 "faculties": {"wcy": {"blocked": false, "cause": null}}}
```

- `status`: `changed` (nowy plan), `unchanged` (taki jak opublikowany), `not_ready` (wydział pokazuje jeszcze inny
  semestr), `gone` (404). Dwa ostatnie są informacyjne i nie są głosami.
- `token_expires`: kiedy wygasa Twój token, żeby koordynator i opiekun mogli ostrzec, zanim crawler zamilknie.
- `faculties`: które wydziały Cię blokowały; przydziały tych wydziałów na kilka godzin przejmują inni.
- `plan`: SHA-256 kalendarza bez linii zmiennych (`DTSTAMP`, `X-PLAN-GENERATED`, `X-PLAN-UPDATED`), więc dwie
  osoby, które widziały ten sam plan, zgadzają się co do bajtu.

**Prywatność:** paczka nigdy nie zawiera surowych stron wydziałów (są na nich nazwiska prowadzących, a fork jest
publiczny), tylko skonwertowane kalendarze, w których nazwisk nie ma (`build.load_term` odrzuca każdy kalendarz z
`CONTACT`, `ORGANIZER`, `ATTENDEE` albo `Prowadzący:` gdziekolwiek w pliku, z tytułem przed nazwiskiem (np. „dr inż.
Kowalski”) w tytule zajęć, opisie, sali czy nagłówku kalendarza oraz z opisem, w którym jest coś poza rodzajem zajęć,
`Uwaga:` i `Grupy:`). Publiczne są (w paczce na forku i w `volunteer-state.json` na gałęzi `data`): Twój
login, czasy przebiegów, które grupy sprawdziłeś i z jakim wynikiem, wersja crawlera, powód ostatniej odmowy, wydziały,
które Cię blokowały, data wygaśnięcia tokenu (sam token nigdy) i dzienne liczniki głosów. Gdy opiekun usunie Cię z
rejestru, następny przebieg koordynatora usuwa Twój wpis z `volunteer-state.json`; login zostaje tylko w polu `by`
grup, które pomogłeś przyjąć (do ich następnego przyjęcia), i w dzienniku przyjęć (do 30 dni). Wcześniejsze wersje
pliku zostają w historii gałęzi `data`.

## Jak sprawdzić, że działa

1. **`planwat-crawler status`**: stan, następny przebieg, ostatni przebieg i werdykt koordynatora, np.
   `Koordynator: the coordinator read the bundle of 2026-10-20T10:40:00: 37 votes, 0 calendars rejected; 120 accepted in 7 days`.
2. **`planwat-crawler doctor`**: każda zależność z ✓ / ! / ✗ i podpowiedzią.
3. **Przebiegi koordynatora** (publiczne): [Actions → Collect volunteer crawls](https://github.com/kilerdevs/PlanWAT/actions/workflows/collect.yml).
   Podsumowanie każdego przebiegu ma tabelę z wierszem dla każdego wolontariusza: paczka przeczytana albo odrzucona
   (z powodem), głosy, przyjęte w 7 dni, blokady i ostrzeżenie o wygasającym tokenie.
4. **Gałąź `data`**, plik `volunteer-state.json`: sekcja `volunteers.<login>` to wszystko, co koordynator wie o Tobie;
   grupy przyjęte z Twoim udziałem mają Twój login w `by`.
5. **Strona grupy**: „Sprawdzono” pokazuje czas ostatniego przyjętego sprawdzenia, także Twojego.

Jako `peer` pierwsze przyjęte wyniki zobaczysz dopiero, gdy ktoś inny sprawdzi te same grupy; przy niewielu
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

Zacznij od `planwat-crawler doctor`: przy każdym ✗ jest podpowiedź. Najczęstsze sytuacje:

| Objaw (`status`, `doctor`, log) | Przyczyna | Co zrobić |
|---|---|---|
| „czeka na wpis do rejestru” | Opiekun jeszcze Cię nie dopisał albo masz poziom „wstrzymany” | Wyślij zgłoszenie z linku w `status`; crawler zacznie sam |
| „wymaga aktualizacji” | Wersja starsza niż `min_version` | `planwat-crawler update` (albo `autoupdate on`) |
| „odsunięty przez koordynatora” | Trzy razy w tygodniu Twój głos przegrał, gdy wszyscy widzieli już nowy plan | Sprawdź wersję; odpisz w issue „Wolontariusz `<login>` niezgodny”, opiekun przywraca |
| `the token cannot see …` / `cannot write to …` | Token nie obejmuje forka albo nie ma Contents: write | `planwat-crawler setup` i nowy token |
| `GitHub does not accept the token` / „token wygasł” | Token wygasł albo został usunięty | Nowy token, `planwat-crawler setup` |
| „paczka z ostatniego przebiegu nie dotarła do forka” | Token, fork albo sieć zawiodły przy wypychaniu (powód w tej samej linii) | `planwat-crawler doctor` sprawdzi token i fork; nowy token: `planwat-crawler setup` |
| „tryb próbny (PLANWAT_DRY_RUN=1)” | Pierwszy, testowy przebieg: nic nie jest wypychane | Po teście usuń `PLANWAT_DRY_RUN` z `.env` i `planwat-crawler start` |
| „ostatnia paczka odrzucona: stale / bad end time” | Bardzo zły zegar albo paczka czekała ponad 12 h | Włącz NTP; następny przebieg wyśle nową |
| „ostatnia paczka odrzucona: not a plain file / not a manifest…” | Ktoś commitował ręcznie na `crawl` | Nie commituj na `crawl`; następny przebieg nadpisze gałąź |
| „odrzucone kalendarze: lost too many events” | Strona wydziału była chwilowo niepełna | Nic; inni (albo kolejny przebieg) potwierdzą właściwy plan |
| `wydział … blokuje Twoje łącze` | Incapsula blokuje Twoje łącze | Nic: przydziały tego wydziału przejmują na razie inni; przy stałej blokadzie poproś o zmianę wydziałów |
| „proxy wyjściowe (egress) nie odpowiada” | Kontener `egress` nie wystartował | `planwat-crawler logs egress` |
| Instalator: „obraz NIE przeszedł weryfikacji” | Obraz nie pochodzi z workflow projektu (albo sieć/GitHub zawiodły) | Nie obchodź tego. Spróbuj później; jeśli się powtarza, zgłoś issue |
| Windows: „Docker Desktop nie odpowiada” | Świeżo zainstalowany WSL2 wymaga restartu | Uruchom ponownie komputer i skrypt |

## Bezpieczeństwo

### Dla Ciebie

- Obraz jest budowany publicznie z tagu wydania (natywnie dla amd64 i arm64) i ma poświadczenie pochodzenia.
  Instalator i aktualizacje sprawdzają je (`gh attestation verify --signer-workflow …/crawler-image.yml`) **zanim**
  cokolwiek w obrazie uruchomią, i przypinają obraz skrótem; aktualizacja, która nie wstaje, jest wycofywana.
- Nie dostajesz żadnego sekretu projektu. Twój token potrzebuje tylko Twojego forka i tylko zawartości; zakres
  wybierasz Ty przy jego tworzeniu (crawler odrzuca tokeny klasyczne, ale zakresu fine-grained nie sprawdzi).
- Crawler nie ma trasy na zewnątrz poza proxy, które wpuszcza wyłącznie GitHub (z magazynem artefaktów Actions na
  `*.blob.core.windows.net`), PyPI i `*.wat.edu.pl` — pełna lista w [EGRESS.md](EGRESS.md) — i nie otwiera żadnego portu
  przychodzącego.
- Paczki są publiczne i opisane Twoim loginem — to, co wysyłasz, widać i da się to audytować. To nie podpis
  kryptograficzny: koordynator przypisuje Ci paczkę, bo leży na gałęzi `crawl` Twojego forka, więc każdy, kto może
  pisać do forka (Ty, Twój token, współpracownik forka), może wysłać paczkę w Twoim imieniu. Chroń token jak hasło.
- Rejestr, który decyduje, co crawlujesz, jest przyjmowany tylko z commita podpisanego przez opiekuna, więc nikt, kto
  przejmie gałąź `volunteers`, nie podsunie Twojemu crawlerowi rejestru, którego opiekun nie podpisał (cofnięcie gałęzi
  do starszej podpisanej wersji odrzuca koordynator i Twój crawler, który pamięta ostatnio użyty commit rejestru).

### Dla serwisu

- **Pojedynczy `peer` niczego nie opublikuje.** Zmowa wymaga dwóch kont zatwierdzonych przez opiekuna, a pary
  zmieniają się co dwie godziny.
- **Każdy kalendarz przechodzi pełną walidację serwisu.** Musi:
  - zbudować się w `build.load_term`;
  - nosić własny kod grupy i nie stracić ponad 40% zajęć;
  - mieścić się w semestrze i nie zawierać nazwisk kadry.

  Strony są escapowane i chronione CSP przypiętym hashami, więc najgorszy możliwy skutek to błędne godziny zajęć, z
  podpisem, kto je dostarczył, i do cofnięcia jednym poleceniem.
- **Stare głosy nie nadpisują nowszego planu.** Głos oddany przed ostatnim zaufanym sprawdzeniem grupy (domowego
  runnera albo przyjętego kworum) jest pomijany, więc wolne kworum nie cofnie świeższego kalendarza.
- **Uczciwe niezgodności nie są karane.** Przegrany głos to „niezgodność” tylko wtedy, gdy oddano go, kiedy zwycięski
  plan już był widoczny; kto widział stronę przed zmianą na wydziale, nie dostaje kary. Czas głosu to deklaracja
  wolontariusza, więc koordynator trzyma go w granicach przebiegu z paczki (i nie wcześniej niż koniec poprzedniej
  paczki), a gdy za zwycięskim planem głosował ktoś zaufany, o tym, kiedy plan był widoczny, decydują tylko czasy
  zaufanych: pojedynczy `peer` nie cofnie swojego czasu, żeby ukarać kogoś innego.
- **Odsunięty nie głosuje.** Odsunięcie usuwa też jego głosy oczekujące w innych grupach.
- **Głos „bez zmian” nigdy nie blokuje zmiany**, którą potwierdziło kworum, więc nie da się zamrozić planu fałszywym
  „nic się nie zmieniło”.
- **Koordynator nie wykonuje niczego z forków.** Najpierw pyta `ls-remote` (paczka bez zmian albo już odrzucona nie
  jest pobierana drugi raz), potem czyta bloby gitem bez checkoutu: tylko HTTPS, bez hooków, z limitem rozmiaru pliku
  na samym pobieraniu (`RLIMIT_FSIZE`), z limitami rozmiaru i listą dozwolonych ścieżek. Jego token nie może
  uruchamiać workflowów ani zmieniać `master`.
- **Koordynator ma budżet.** Jeden przebieg pobiera najwyżej 400 MB i po 10 minutach nie zaczyna nowych pobrań
  (reszta czeka na następny przebieg, najdawniej pobierani pierwsi), w pamięci trzyma naraz tylko kilka paczek, a fork
  jednej osoby pobiera najwyżej 24 razy na dobę. Paczka, która wywraca sprawdzanie (zła wersja, zbyt głęboki JSON),
  jest odrzucana, a przebieg idzie dalej.
- **Czego to nie rozwiązuje:** wolontariusz nie może *udowodnić*, że strona pochodzi z WAT. Wymagałoby to
  notaryzacji TLS, a to tutaj przesada. Obroną jest kworum, tożsamość z rejestru i rozliczalność. Tak samo czasy w
  paczce są deklaracją: gdy za planem głosowali sami `peer`owie, jeden z nich może przesunąć swój czas w obrębie
  własnego przebiegu.

Szczegóły modelu zagrożeń: [SECURITY.md](../SECURITY.md).

## Dla opiekuna

### Panel uprawnień

Uprawnienia zmieniasz w przeglądarce, w panelu uruchamianym z własnego klonu repozytorium:

```sh
python3 tools/volunteer/manage.py
```

Otwiera się strona (adres z jednorazowym tokenem jest też w terminalu), na której:

- widzisz każdego wolontariusza z jego stanem u koordynatora: czy działa (paczka w ostatnich 6 h), wersję crawlera
  (z ostrzeżeniem poniżej `min_version`), ostatnią odmowę albo powód odrzucenia kalendarzy, blokady wydziałów,
  wygasający token, przyjęte kalendarze w 7 dni, niezgodności w tym tygodniu i to, czy został odsunięty;
- karta **Pokrycie** pokazuje dla każdego wydziału, ile grup bieżącego semestru nikt zaufany nie sprawdził od doby;
- przełączasz poziom: **Zaufany / Równorzędny / Wstrzymany**, i wybierasz wydziały (albo „Wszystkie”);
- dodajesz osobę (login i fork; panel zapisuje datę dodania, od której liczy się doba na pierwszą paczkę) albo ją usuwasz;
- zmieniasz zasady głosowania: kworum, ważność głosu, najstarszą wersję crawlera;
- przywracasz odsuniętego wolontariusza jednym kliknięciem (uruchamia `collect.yml` z `unbench`; potrzebny `gh` po `gh auth login`).

Pasek na dole pokazuje, co się zmieni. **Zapisz i opublikuj** robi jeden commit z samym `volunteers.json`,
**podpisany Twoim kluczem** (ten sam co dla `master`), i wypycha go na gałąź `volunteers`. Zmiana działa od
najbliższego przebiegu koordynatora, czyli najpóźniej po 30 minutach, bez wydania i bez PR. Pierwszy zapis tworzy
gałąź (z `min_version` równą wersji Twojego klonu, nigdy wyższą niż istniejące wydanie). Jeśli w międzyczasie ktoś
zmienił rejestr, panel odmówi zapisu i poprosi o odświeżenie. Po wypchnięciu panel pyta GitHuba, czy uznaje commit za
podpisany przez opiekuna; jeśli nie, mówi to od razu (inaczej koordynator i crawlery po cichu by go odrzucały). Gdy nie
da się pobrać gałęzi, panel mówi to zamiast udawać nowy projekt, a nieczytelny `volunteers.json` pokazuje z propozycją
zastąpienia go przy zapisie.

Panel słucha tylko na `127.0.0.1`, wymaga tokenu z adresu i odrzuca żądania z innym nagłówkiem `Host`.

**Dlaczego to bezpieczne bez PR:** koordynator bierze rejestr tylko z commita, który GitHub weryfikuje jako podpisany
przez osobę z listy `REGISTRY_EDITORS` w `collect.yml`. Ta lista leży na chronionym `master`, więc token, który może
wypychać gałęzie (domowego runnera albo samego koordynatora), nie nada nikomu zaufania. Inny commit na gałęzi
`volunteers` zatrzymuje koordynatora z błędem, zamiast zostać użyty. Tak samo cofnięcie gałęzi (force push) do
starszego, choć podpisanego commita: koordynator zapisuje w `volunteer-state.json` commit rejestru, którego użył, i
przyjmuje tylko ten sam albo nowszy. Jeśli kiedyś celowo przepiszesz historię `volunteers`, zrób po tym jeszcze jeden
zapis w panelu na wierzchu commita z pola `registry.sha` albo usuń to pole z `volunteer-state.json`. Chroń też samą
gałąź (Settings → Rules → New branch ruleset, cel `volunteers`: ogranicz aktualizacje do siebie, zablokuj force push i
usuwanie, wymagaj podpisanych commitów): token, który pisze na `data`, mógłby podmienić i zapisany commit.

### Pozostałe przełączniki

- **Przyjęcie wolontariusza:** po zgłoszeniu dopisz go w panelu (domyślnie jako równorzędnego). `CODEOWNERS` wymaga
  Twojej recenzji dla całego kodu crawlowania.
- **Włączenie publikowania:** dopóki zmienna repozytorium `PLANWAT_COLLECT_LIVE` nie ma wartości `true`, każdy
  przebieg `collect.yml` jest próbny: loguje, co by przyjął, niczego nie zapisuje i nie otwiera issue o odsunięciu.
  Ręczne `revert` i `unbench` (Run workflow) to Twoje polecenia i zapisują zawsze, także przy wyłączonym
  publikowaniu, żeby awaryjne cofnięcie działało. Settings → Secrets and variables → Actions → Variables.
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
- **Uszkodzony `volunteer-state.json`** (nie da się go odczytać) zatrzymuje każdy przebieg, `revert` i `unbench` z
  błędem, zamiast zostać nadpisany pustym stanem. Przywróć plik z historii gałęzi `data` (albo usuń go, by zacząć od
  zera: przepadną głosy, niezgodności, odsunięcia i dziennik do `revert`).

## Rezygnacja

1. `planwat-crawler uninstall` (usuwa kontenery, dane i harmonogram aktualizacji). W trybie B: wyrejestruj runner i
   wyłącz workflow w forku.
2. Usuń token (Settings → Developer settings → Fine-grained tokens → Delete).
3. Usuń gałąź `crawl` z forka, jeśli chcesz.
4. Napisz w swoim zgłoszeniu — opiekun usunie Cię z rejestru, a następny przebieg koordynatora usunie Twój wpis z
   `volunteer-state.json` (zob. „Prywatność” wyżej).

Dziękujemy!

<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Automatyczna aktualizacja planów

**Plany są ponownie czytane ze stron wydziałów i publikowane bez commita na `master` ani `dev`.**

[![Refresh](https://github.com/kilerdevs/PlanWAT/actions/workflows/refresh.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/refresh.yml)
![Runnery](https://img.shields.io/badge/runnery-2%20self--hosted%20(podzia%C5%82%20pracy)-blue?style=flat)
![Harmonogram](https://img.shields.io/badge/harmonogram-co%202%20godziny-informational?style=flat)
![Grupy](https://img.shields.io/badge/grupy-781-brightgreen?style=flat)
![Dane kadry](https://img.shields.io/badge/dane%20kadry-brak-critical?style=flat)

</div>

Zaplanowany workflow GitHub Actions czyta strony wydziałów, konwertuje plany, sprawdza je i wypycha na gałąź `data`.
Workflow Pages nakłada te kalendarze na strony przy każdej budowie.

<img src="diagrams/aktualizacja-planow.svg" alt="Codziennie w nocy runner odczytuje strony wydziałów przez proxy, konwertuje plany, waliduje je i wypycha na gałąź data. Pages nakłada je na strony i publikuje." width="760">

```
refresh.yml   co 2 godziny (`23 */2 * * *`), na własnych runnerach (wydziały dzielone między włączone): crawl → konwersja → walidacja → push na `data`
gałąź data    timetables/<semestr>/<GRUPA>.ics oraz refresh-state.json
pages.yml     pobiera `data` i nakłada jej plany na prod/ i dev/ przed uruchomieniem build.py
```

<img src="diagrams/przebieg-odswiezania.svg" alt="Los jednej grupy: kolejka, pobieranie, konwersja, walidacja i publikacja. Brak zmian, blokada z odczekaniem oraz błąd walidacji kończą się bez nowego commita." width="760">

## Jak zachowuje się przebieg

- Jedna sesja, jedno żądanie naraz, losowa przerwa między stronami (1,5–4 s na własnym runnerze, 4–9 s z `--profile hosted`),
  honorowany `robots.txt`, warunkowa rewalidacja (`If-Modified-Since` / `ETag` zapamiętane dla każdej grupy, więc niezmienione
  strony odpowiadają `304` bez treści), pomijanie grup sprawdzonych mniej niż 60 minut temu (`--fresh-hours`) oraz rozciąganie
  przerwy przed następnym sprawdzeniem cichej grupy (`--adaptive-hours`, w akcji 4 h — niżej), więc w spokojnym semestrze
  przebieg zagląda do cichej grupy rzadziej niż co drugi raz. Wszystkie polityki Incapsula (`--lanes`, domyślnie 6) są przeglądane
  równolegle, każdy host we własnym tempie, więc pełny przebieg trwa krócej niż godzinę. Po zakończeniu przebiegu
  `pages.yml` (`workflow_run`, etap „rebuild needed?”) od razu odbudowuje stronę, gdy zmienił się choć jeden kalendarz.
  Przebieg, który zapisał tylko nowe godziny sprawdzeń (prawie każdy wypycha `refresh-state.json`), odbudowuje ją dopiero
  wtedy, gdy opublikowana wersja ma ponad 6 h (`STAMPS_MAX_HOURS`): „Sprawdzono” spóźnia się wtedy najwyżej o tyle, a
  strona nie jest wdrażana kilkanaście razy dziennie dla samej godziny. Przebieg, który nic nie wypchnął, nie wdraża nic.
  Wyjątek: przebieg, który skończył się inaczej niż poprzedni (inny wynik albo inne serwery, `history=new`), odbudowuje
  stronę od razu, żeby [`/stan/`](#historia-przebiegów) go pokazała.
- **Blokada odkłada wydział, nie kończy przebiegu.** Każdy status inny niż 200 (z wyjątkiem 304 i 404) albo strona incydentu
  Incapsula to najpierw odpowiedź blokady, nie wyrok: crawl zgłasza ją do proxy wyjściowego (które wycofuje wyjście, jakie ją
  przewiozło — w tunelu CONNECT proxy nie widzi strony blokady), a potem ponawia na świeżym połączeniu, czyli na innym wyjściu
  rotującej puli (`--block-retries`, domyślnie 2). Dopiero blokada, która przetrwa wszystkie próby, zawiesza wydział, podczas
  gdy pozostałe są obsługiwane, a potem odczekuje blokadę i wznawia od miejsca
  przerwania. Długość snu jest wyuczona dla każdej grupy polityki z poprzednich odbudowań (mediana, 20 min – 12 h, 2 h bez historii;
  epizody „ściany” ważą więcej niż niestabilne), odblokowanie jest sprawdzane tanimi pobraniami indeksu w rzadko-potem-gęsto
  rozłożonym harmonogramie (`--block-probes`, domyślnie 5, zawsze w ramach pozostałego budżetu), a całe oczekiwanie jest
  ograniczone (`--max-block-wait-minutes`, domyślnie 30, przy równoległych wydziałach każdy czeka osobno, a przy kolejnych dzielone sprawiedliwie: każde czekanie dostaje swój udział, ale co
  najmniej 15 min). Nic niedokończonego nie jest publikowane. Ostatnie poprawne kalendarze
  zostają, zgłoszenie GitHub otwiera się tylko wtedy, gdy przebieg kończy się wciąż zablokowany, a zadanie na własnym runnerze
  próbuje później ze stanu, który zapisał. (Znaczniki `_Incapsula_Resource` na dobrych stronach nie są blokadą.)
  Tylko przejściowe pobrania (błędy transportu, 408/425/429/500/502/503/504, pusty 200) są najpierw ponawiane z odczekaniem
  (`--retries/--retry-backoff`). Wyczerpanie odróżnia ścianę (`cause: wall`) od chwiejności
  (`cause: flaky`), a kolejka idzie od najdawniej sprawdzonych, więc przerwany przebieg zawsze obejmuje najdłużej niewidziane
  grupy. WLO i WEL dzielą jedną politykę Incapsula (`wat-edge`): jedno oczekiwanie obejmuje oba, potem każdy wznawia na własnej
  świeżej sesji. Wyuczony czas ochłodzenia zastąpił dawną stałą regułę 24–48 h (stan zachowuje przez ten czas ostatnie
  poprawne kalendarze).
- **Postęp na żywo w panelu egressu.** Przebieg wysyła najlepszym wysiłkiem na `POST /api/progress` egressu
  (`PLANWAT_EGRESS_PROGRESS`, ustawiany w akcji odświeżania; puste wyłącza) grube zdarzenia: start przebiegu z układem
  ścieżek, start wydziału z liczbą grup, przycinane próbki postępu (≈4 s na wydział), koniec wydziału (z blokadą albo
  niepełnością; przejście nadchodzącego semestru dostaje osobny slot „wydział~semestr”) oraz początek i koniec oczekiwania na
  odblokowanie. Panel liczy z nich pasek postępu i przewidywany koniec (zob. docs/EGRESS.md). To dodatek: brak egressu albo
  zgubione zdarzenie niczego nie psuje.
- **Pogorszony przebieg mówi o tym głośno.** Pięć i więcej sprawdzeń z ponad 30% pominiętych albo grupa z listą mniejszą niż
  połowa poprzedniej (od 10 pozycji) oznacza wydział jako `degraded`: przebieg kończy się jako niepełny i eksportuje
  `degraded=true`.
- **Tempo i częstotliwość dostosowują się.** `--fresh-hours` (nadpisywalne dla wydziału, nigdy poniżej 1 h) zmniejsza się o
  połowę w sierpniu, styczniu i lutym, gdy wydziały publikują nadchodzący semestr. Przerwa między stronami skaluje się dla
  każdej grupy polityki (AIMD: ×1,5 przy blokadzie do 3×, ×0,9 przy czystym wydziale do 1×).
- **Ciche grupy wydłużają sobie przerwę, zmieniające wracają na pełne tempo.** Każde zakończone sprawdzenie, po którym plan
  wyszedł ten sam (również `304`), podwaja przerwę przed następnym sprawdzeniem tej grupy: 1 h, 2 h, 4 h… — do sufitu
  `--adaptive-hours` (w akcji 4 h; 0 wyłącza rozciąganie i przywraca sprawdzanie przy każdym przebiegu). Miesiące publikacji
  (połowa `--fresh-hours`) podsuwają całą drabinkę na dwukrotnie niższy start, więc nadchodzący semestr jest sprawdzany
  częściej. Zmiana planu zeruje przerwę: grupa natychmiast wraca do sprawdzania przy każdym przebiegu. Grupy „jeszcze
  nieopublikowane” i strony z upadłą konwersją nie dostają stempla „sprawdzono”, więc czeka na nie sprawdzanie przy każdym
  przebiegu — to one niosą publikowany nowy semestr.
- Strona jest publikowana tylko wtedy, gdy kalendarz przechodzi własną walidację serwisu (`build.load_term`), nosi kod grupy
  swojego pliku i nie stracił więcej niż 40% zdarzeń. W przeciwnym razie stary kalendarz zostaje, a grupa trafia do logu.
- Kalendarz jest nadpisywany tylko wtedy, gdy plan się zmienił (data wygenerowania jest ignorowana), więc historia `data`
  pokazuje prawdziwe zmiany planu.

## Wydziały

Wydziały wymienia `tools/refresh/sources.json`. Każdy wskazuje sterownik w `tools/refresh/drivers/`:

| Wydział | Sterownik | Stan |
|---|---|---|
| WLO, WEL, WIM | `plansoft` | włączone |
| IOE | `plansoft` (przypięta baza: zimowe plany leżą pod nieaktualnym katalogiem `lato/`, siatka jest transponowana, a jej komórki odczytywane jako PRZEDMIOT/rodzaj/sala/alias, konwertowane przez `wlo2ics --faculty ioe`) | włączone |
| WML | `wml` (strony Plansoft, żywy `index.xml` rozpoznawany przez ramkę strony głównej, bo wydział publikuje ponownie w katalogach z rewizją) | włączone |
| WCY | `wcy` | włączone: zwykłe HTTP działa (sprawdzono 14.10.2026), a strony pokazujące inny semestr (lub pustą siatkę) są liczone jako „jeszcze nieopublikowane” — stare kalendarze zostają do publikacji nowego planu i nie oznaczają przebiegu jako pogorszony; stary kalendarz jest przed porównaniem przycinany do semestru, więc oczyszczenie pliku niosącego jeszcze lekcje poprzedniego lata nie jest czytane jako podejrzany skurcz planu |
| WTC | `wtc` | włączone: płaski `index.xml` (`/Plany/`) nazywa semestr, który wymienia (`<period>`), a sterownik publikuje PDF-y tylko dla odświeżanego semestru; konwersja przez `pymupdf` (instalowany przez akcję odświeżania) |
| WIG | `wig` | włączone: otwarte listingi katalogów Phoca Download (`/cpp/phocadownloadpap/`), w nich PDF-y będące wydrukami stron Plansoft; sterownik odtwarza siatkę z linii tabeli i oddaje ją `wlo2ics`, a semestr i grupę bierze z nagłówka PDF-u (`pymupdf`, jak przy WTC) |

Każda grupa ma dokładnie jednego kanonicznego właściciela, więc żaden plan nie jest publikowany dwa razy pod dwoma kodami: WEL
pomija strony `IOE*` i `WME*`, które jego indeks też wymienia (należą do IOE i WIM), a IOE pomija wymienioną stronę `WME*`.
Odwrotnie jest z grupami `WIG..BW` (budownictwo, studia wojskowe): wymienia je i WEL, i WIG, ale kopia WEL jest świeższa i
ustrukturyzowana, więc zostają przy WEL, a WIG je pomija.

Strony nazwane jak `1PL26KP` dostają prefiks wydziału (`WEL1PL26KP`), żeby nazwa pliku, `X-PLAN-GROUP` i sekcja na stronie
głównej były spójne. Strony niebędące kodami grup (kursy, np. `Kurs_-_…`) są pomijane. Grupy WML zachowują własne kody `WMT`
wydziału (crawl obejmuje tylko strony `^WMT`) i są wyświetlane w sekcji WML. Grupy WIM zachowują swoje kody `WME` i są
wyświetlane w sekcji WIM.

Uwagi o WTC: serwis stoi za Incapsulą, a publiczne wyjścia puli dostają od niego blokady, podczas gdy linia domowa odpowiada
normalnie. Dlatego WTC — podobnie jak pozostałe wydziały poza WCY — jest na liście ruchu bezpośredniego proxy wyjściowego
(`EGRESS_DIRECT_FACULTY`, zob. docs/EGRESS.md), a przez pulę musi iść wyłącznie WCY. Indeks wydziału jest płaski
(`https://wtc.wat.edu.pl/Plany/index.xml`) i nazywa semestr, który wymienia; sterownik plikuje PDF-y tylko wtedy, gdy to
odświeżany semestr, a pobiera je z indeksem jako Referer, po jednym naraz. Konwerter wymaga `pip install pymupdf` na każdej
maszynie uruchamiającej crawl (codzienna akcja instaluje go do jednorazowego venv w `$RUNNER_TEMP`, bo wbudowany w runner
`/opt/venv` jest w trakcie zadania tylko do odczytu). Skonwertowane kalendarze nie zawierają nazwisk kadry (zob. zasadę
prywatności niżej).

Uwagi o WIG: wydział nie ma indeksu planów. Strona `rozklady-zajec` (Joomla) linkuje PDF-y grup z kategorii kierunków i
roczników, ale same pliki leżą w zwykłych katalogach (`/cpp/phocadownloadpap/<kierunek>/<tryb>/WIG26AX1S0.pdf`, tryb
`stacjonarne`, `niestacjonarne` albo `drugistopien`) z otwartymi listingami Apache. Wykrywanie czyta te listingi, nie
Joomlę: Incapsula odpowiada na strony Joomli wyzwaniem (403) z adresów centrów danych (runner oracle, sprawdzono
26.10.2026), a listingi i PDF-y podaje obu runnerom; dwa poziomy małych listingów są też tańsze niż 60 stron kategorii.
Listing ponad kierunkami jest ukryty, więc katalogi kierunków wymienia `dirs` w `sources.json`, a ich podkatalogi trybów
znajduje przejście. Żeby nowy kierunek nie umknął, plebania robi **spis** (`--census wig`, `census` w `fleet.json`, najwyżej
raz na dobę): przechodzi drzewo Joomli, które jej łącze widzi, i zapisuje katalogi wszystkich wymienionych tam PDF-ów w
`refresh-state.json` (`found`). Wykrywanie czyta je razem z `dirs` na każdym runnerze, więc grupa nowego kierunku trafia na
stronę w pierwszym przebiegu po spisie, nawet gdy WIG crawluje oracle. Spis loguje katalogi spoza `dirs` do dopisania;
zablokowany albo nieudany spis zostawia poprzedni i nie psuje przebiegu (26.10.2026 jedynie „Bud. dróg i mostów” nie miał
jeszcze żadnego katalogu). Katalog, który zniknął, nic nie wymienia, a spadek liczby grup o ponad połowę oznacza przebieg
jako `degraded`. PDF-y to statyczne pliki z `Last-Modified`, więc niezmieniony plan odpowiada `304`. Każdy PDF jest wydrukiem (wkhtmltopdf) strony Plansoft w jednym
z dwóch układów: stacjonarne powtarzają dzień w każdym wierszu, niestacjonarne rozciągają jedną komórkę dnia na wiersze
dnia. Sterownik odtwarza tabelę z linii siatki i słów w komórkach, skleja wiersz przecięty przez koniec strony, rozpoznaje
kolumny po treści (dzień, blok, daty) i oddaje zwykłą stronę Plansoft konwerterowi `wlo2ics`. Rok akademicki pochodzi z
nagłówka PDF-u (`SEMESTR - WIG ZIMA 2026-2027`), nie z daty aktualizacji, bo plany niestacjonarne drukowane są w sierpniu.
PDF innej grupy jest odrzucany, a PDF innego semestru liczy się jako „jeszcze nieopublikowany” (`core.NotReady`).

## Bez nazwisk kadry w kalendarzach

Opublikowane kalendarze nie zawierają danych osobowych kadry: konwertery nigdy nie zapisują linii `CONTACT` ani linii z
prowadzącym (`Prowadzący:`). Nazwiska nauczycieli ze stron wydziałów są wyłącznie wynikiem pośrednim parsowania (sterują
podziałem na salę i nauczyciela) i są odrzucane, zanim kalendarz zostanie zapisany. `build.py` odrzuca każdy kalendarz, który
wymienia kadrę, więc regresja psuje budowę zamiast publikować nazwiska.

## Jednorazowa konfiguracja

1. Utwórz gałąź `data` z aktualnych poprawnych planów:
   `git switch --orphan data && git checkout dev -- timetables && git commit -m "Seed timetables" && git push -u origin data`
   (zostaw tylko kalendarze, które przechodzą `python build.py`).
2. Settings → Actions → General: zezwól GitHub Actions na tworzenie zgłoszeń i uruchamianie workflowów (uprawnienia workflowów
   „Read and write”) oraz ustaw „Fork pull request workflows” na wymaganie zatwierdzenia.
3. Wypróbuj: Actions → *Refresh timetables* → Run workflow, wydział `wim`.

## Własne runnery

Ściana Incapsula na stronach wydziałów blokuje adresy centrów danych GitHub już przy pierwszym żądaniu (widziane przy pierwszym
przebiegu na hostowanym runnerze: `index.xml` odpowiedział 403), więc crawl działa wyłącznie na własnych runnerach (etykieta
`planwat`), które ściana przepuszcza.

Runner nawiązuje tylko połączenia wychodzące do GitHub, a maszyna **nie potrzebuje żadnego otwartego portu przychodzącego**.
Każdy, kto może uruchomić workflow w repozytorium, może uruchomić kod na runnerze, więc:

- workflow uruchamia go tylko dla `schedule` i `workflow_dispatch` (nigdy dla pull requestów), a uruchamiać mogą tylko osoby z
  prawem zapisu;
- uruchamiaj go w kontenerze jako użytkownik bez uprawnień, bez montowań hosta, bez gniazda Dockera i bez żadnych sekretów poza
  własną rejestracją; zarejestruj go na poziomie repozytorium z etykietą `planwat`;
- zablokuj cały ruch przychodzący do hosta i zezwól na wychodzący wyłącznie do GitHub i hostów wydziałów.

### Dwa runnery i podział pracy

Projekt ma dwa runnery, opisane w [`tools/refresh/fleet.json`](../tools/refresh/fleet.json):

| Runner | Etykieta | `speed` | Charakter |
|---|---|---|---|
| plebania | `planwat-plebania` | 4 | prywatny serwer: szybki, ale często wyłączony |
| oracle | `planwat-oracle` | 1 | darmowy VPS ([deploy/runner/](../deploy/runner/README.md)): wolny i słaby, ale zawsze włączony (`always_on`) |

Każdy przebieg `refresh.yml` ma pięć etapów (udział jednego runnera to wspólny workflow `refresh-crawl.yml`):

1. **plan** (runner GitHub, bez dostępu do wydziałów): pyta API GitHub, które runnery są `online`, i dzieli między nie
   ścieżki polityk Incapsula (`tools/refresh/fleet.py plan`). Ścieżka nigdy nie jest dzielona (WLO i WEL stoją za jedną
   ścianą i czekają razem). Praca ścieżki to liczba grup, które jej wydziały wymieniły ostatnio, razy wyuczony mnożnik
   tempa. Ścieżki idą od największej, każda do runnera, który skończy ją najwcześniej (obciążenie / `speed`), więc
   szybka plebania bierze większość, a VPS resztę, i oba kończą mniej więcej razem. Wyłączony runner nie dostaje nic,
   więc żadne zadanie nie czeka w kolejce na maszynę, która nie przyjdzie. Gdy nic nie jest włączone, przebieg niczego
   nie crawluje, a następny planuje od nowa. Podział widać w podsumowaniu zadania. Gdy jest włączony drugi runner, który
   mógłby przejąć wydział, plan każe czekać na zejście ściany tylko 5 minut zamiast 30 (`max-block-wait-minutes`):
   zamiast czekać, lepiej oddać wydział.
2. **crawl** (po jednym zadaniu na runner, macierz): każdy runner crawluje swoje wydziały (`--faculty`) i wypycha wynik na
   `data`. Runnery wypychają równolegle, więc push nie robi rebase: każda próba zaczyna od najnowszego commita gałęzi,
   kładzie na nim kalendarze tego przebiegu i scala `refresh-state.json` (`fleet.py merge`: stemple grup zmienione w tym
   przebiegu, a stan łącza tylko dla własnych wydziałów), do pięciu prób. Zadanie, które dostało runnera później niż 30
   minut po planie (maszyna zgasła tuż po tym, jak GitHub ją widział, i wróciła później), niczego nie crawluje: nowsze
   przebiegi zaplanowały już bez niej. Współbieżność jest na runner, nie na workflow, więc takie zawieszone zadanie nie
   blokuje kolejnych przebiegów. Limit czasu (`--max-minutes`, 90 minut) obejmuje cały udział razem z czekaniem na
   ściany, nie każdy wydział osobno: po nim każda ścieżka kończy bieżącą stronę, a runner zapisuje i wypycha to, co ma,
   zanim GitHub przerwie zadanie po 110 minutach. Czego nie zdążył, przejmuje handoff.
3. **handoff** (runner GitHub, po crawl): ściana Incapsula stoi przed jednym adresem, nie przed wydziałem, więc to, co
   runner zostawił **zablokowane** albo **niedokończone** (limit czasu, awaria, udział, który w ogóle nie ruszył), dostaje
   inny runner. Dotyczy to też udziału, który GitHub anulował w kolejce (współbieżność na runner). Zadanie pyta API
   GitHub **jeszcze raz**, kto jest teraz `online` (plebania mogła się w międzyczasie włączyć albo zgasnąć), i dzieli
   zostawione ścieżki tak jak plan (`fleet.py handoff`). Liczy się tylko runner, który ma też etykietę `planwat`, bo bez
   niej zadanie nigdy by na niego nie trafiło. Wydział nie wraca do runnera, który go zostawił; ścieżka (np. WLO z WEL)
   przechodzi w całości. Każdy runner zgłasza w wyniku dokładnie, które wydziały zostawił zablokowane i których nie
   skończył (`blocked_faculties`, `incomplete_faculties` z `refresh.py`). Jedyny wyjątek: jeśli runner oddał
   zablokowaną ścieżkę po krótkim czekaniu, bo plan widział drugi runner, a ten zdążył zgasnąć, ścieżka wraca do niego
   na resztę czekania (25 minut), o ile nadal jest włączony. Wtedy każdy wydział i tak dostaje pełne 30 minut. Bez
   drugiego włączonego runnera wydział, który miał już pełne czekanie, czeka na następny przebieg, jak dawniej.
   Anulowanie całego przebiegu zatrzymuje handoff i przejęcie.
4. **takeover** (macierz, tak jak crawl): przejmujący runner crawluje te wydziały, czekając na ścianę pełne 30 minut, bo
   po nim nikt już ich nie przejmie. Zaczyna tam, gdzie poprzedni skończył: grupy, które tamten sprawdził i wypchnął, są
   świeże i zostają pominięte. Przejmowanie jest jednokrotne (jeden etap), więc przebieg nie może krążyć w kółko.
5. **report** (runner GitHub): sumuje wyniki runnerów do `refresh-outcome.json` dla bramki `pages.yml` (brak wyniku
   któregoś runnera = przebudowa) i otwiera albo zamyka zgłoszenia o blokadzie i degradacji. Wydział liczy się tak, jak
   zostawił go ostatni runner, który go miał: zablokowany na oracle i czysto przejęty przez plebanię nie blokuje
   przebiegu. Przebieg, w którym jakiegoś wydziału nikt nie skończył, jest niepełny: niczego nie zamyka. Przebieg starszy niż 3 h zostawia zgłoszenia nowszym. Na koniec
   zapisuje przebieg w [historii przebiegów](#historia-przebiegów).

Runner może też **preferować** wydziały (`prefers` w `fleet.json`): ścieżkę złożoną z nich dostaje zawsze, gdy jest
włączony, niezależnie od obciążenia. Gdy jest wyłączony albo to on ją zostawił (handoff), ścieżka jest dzielona jak każda
inna. Oracle preferuje WIG i IOE: oba runnery przeszły 26.10.2026 po dwa przebiegi WIG (33 z 33 grup, identyczne kalendarze), a
IOE z oracle przeszedł czysto 9 przebiegów z 9. Plebania preferuje WTC, bo ściana WTC odrzuca adres VPS (zablokowany w 4
przebiegach z 4, zwykłe HTTPS z maszyny dostaje 403): na oracle WTC kosztował tylko czekanie na ścianę i przekazanie.
Przy obu włączonych oracle dostaje WIM, IOE i WIG, a plebania WLO z WEL, WCY, WML i WTC. Runner może też robić **spis** wydziału
(`census`): plebania robi spis WIG, bo tylko jej łącze widzi strony Joomli wydziału (zob. uwagi o WIG wyżej).

Każdy runner ma też **własny stan łącza** (wyuczone tempo, czasy blokad, ostatni przebieg wydziału): różne adresy
trafiają na różne ściany, więc trzyma go w `$RUNNER_TOOL_CACHE/planwat/refresh-line.json`, zasiany raz z gałęzi `data`.
Na `data` trafia stan łącza tego runnera, który ostatnio crawlował dany wydział.

Konfiguracja (jednorazowo):

1. Etykiety: Settings → Actions → Runners → runner → Labels. Plebanii dodaj `planwat-plebania`, VPS-owi `planwat-oracle`
   (obaj zostają też przy `planwat`). Nowy runner z [deploy/runner/](../deploy/runner/README.md) dostaje je przy
   rejestracji z `RUNNER_LABELS`.
2. Token do sprawdzania, kto jest włączony: fine-grained personal access token tylko do tego repozytorium z jednym
   uprawnieniem **Administration: Read-only** (listy runnerów nie da się odczytać `GITHUB_TOKEN`). Zapisz go jako sekret
   Actions `PLANWAT_RUNNERS_TOKEN`. Bez niego (albo gdy API zawiedzie) wszystko bierze runner `always_on`, jak dawniej
   jedyny runner.
3. Dostrajanie: kolumna „minutes” w podsumowaniu zadania report pokazuje, ile trwał udział każdego runnera. Gdy jeden
   regularnie kończy dużo później, zmień `speed` w `fleet.json`. Pole `faculties` (lista) ogranicza runner do tych
   wydziałów, np. gdy któryś wydział nie wpuszcza adresu VPS-a.

### Historia przebiegów

Ostatnie 10 przebiegów widać w dwóch miejscach, z tego samego pliku:

- **na GitHubie:** [`README.md` gałęzi `data`](https://github.com/kilerdevs/PlanWAT/blob/data/README.md) (i w podsumowaniu
  każdego przebiegu). Na górze stan ostatniego przebiegu jako alert GitHub, niżej tabela i rozwijane szczegóły;
- **na stronie:** [`/stan/`](https://kilerdevs.github.io/PlanWAT/stan/), podlinkowana w stopce strony głównej. Strona nie
  uruchamia żadnego skryptu: wiersze rozwijają się elementem `<details>`.

Każdy przebieg pokazuje, kiedy ruszył i jak się skończył (bez zmian, zmiany w N planach, część stron odrzucona, niedokończony,
zablokowany albo „serwery wyłączone”), **które serwery go zrobiły** (plebania, oracle: wydziały każdego, czas, stan) i które
były wtedy wyłączone, a dla każdego wydziału: ile grup sprawdzono i zmieniono, ile nie ma jeszcze planu na ten semestr, ile
stron odrzucono i czy była blokada. Liczby wydziału pochodzą z jego wpisu `run` w `refresh-state.json`, o ile powstał w tym
przebiegu; inaczej wydział ma „brak danych z tego przebiegu”.

`/stan/` pokazuje też **stan opublikowanych planów** (z `refresh-state.json`, liczony na koniec ostatniego przebiegu, więc
strona zbudowana później mówi to samo): jak dawno sprawdzono plany każdego wydziału, dzień ostatniej zmiany planu z 14
dni, plany najdawniej sprawdzone (dzień lub więcej), ostatnio zmienione i najdłużej bez zmian. Plan, którego wydział nie
potwierdził w tym semestrze (strona pokazuje jeszcze inny semestr), liczy się osobno jako „bez potwierdzenia”. Wykresy są
w SVG bez skryptu, z tabelą liczb pod każdym.

Zapisuje je zadanie **report** (`tools/refresh/runs.py record`): dopisuje przebieg do `refresh-runs.json` na `data` (od
najnowszego, ponowna próba zastępuje pierwszą, najwyżej 10) i przepisuje z niego `README.md` gałęzi. Push ma tę samą pętlę
co runnery (najnowszy commit gałęzi, do pięciu prób), a błąd tutaj nigdy nie psuje raportu. `pages.yml` kopiuje plik obok
`refresh-state.json`, a `build.py` renderuje z niego `/stan/` (lokalnie: `python3 build.py --runs <plik>`; bez pliku strona
mówi, że historii jeszcze nie ma, a link prowadzi do listy przebiegów workflow). Strona odświeża się razem z witryną.
Przebieg, który skończył się inaczej niż poprzedni (inny wynik, np. blokada albo powrót do normy, albo inny zestaw
serwerów, np. plebania się włączyła) albo zmienił plany, odbudowuje ją od razu: `runs.py record --outcome` dopisuje wtedy
`history=new` do `refresh-outcome.json`, a bramka Pages to czyta. Pierwszy przebieg w historii też się liczy. Przebieg taki
jak poprzedni czeka na regułę 6 h (`STAMPS_MAX_HOURS`), więc wtedy `/stan/` bywa za GitHubem do kilku godzin.

## Gdyby sam GitHub został przejęty

Projekt zakłada, że repozytorium (kod, Actions, gałąź `data`, `GITHUB_TOKEN`) może wpaść w niepowołane ręce, podczas gdy host
runnera musi pozostać czysty, a opublikowana strona bezpieczna:

- Runner żyje w wewnętrznej sieci Docker bez trasy na zewnątrz, a jego jedyne wyjście to proxy, które zezwala na
  `CONNECT ...:443` wyłącznie do GitHub, PyPI i hostów wydziałów (cokolwiek innego, w tym gołe adresy IP, dostaje `403 Filtered`).
  Ukradziony token zadania nadal nie sięgnie bezpośrednio do serwera atakującego, a eksfiltracja ogranicza się do wypchnięcia do
  GitHub, co da się audytować w historii repozytorium.
- Token zadania na runnerze ma tylko `contents:write` (push gałęzi `data`); zgłoszenia o blokadzie otwiera zadanie report
  na runnerze GitHub (`issues:write`). Celowo nie ma
  `actions:write`: odświeżone kalendarze podbiera codzienna przebudowa `pages.yml`, więc skradziony token nie może uruchamiać ani
  zatwierdzać innych workflowów.
- Sekret `PLANWAT_RUNNERS_TOKEN` (zadanie plan, na runnerze GitHub) pozwala tylko czytać ustawienia administracyjne tego
  repozytorium, w tym listę runnerów: wyciek pokazuje konfigurację, ale niczego nie zmieni. Nie trafia na własne runnery.
- `master` jest chroniony (podpisane commity, wymagane CI), a `pages.yml` buduje produkcję wyłącznie z `master`, nakładając
  kalendarze z `data`, z których każdy musi przejść walidację `build.load_term` i jest escapowany do stron z CSP przypiętym
  hashami. Zatruta gałąź `data` nie może więc wstrzyknąć skryptu ani wypromować treści do katalogu głównego: w najgorszym razie
  pokaże błędne godziny zajęć do czasu cofnięcia. Chroń też gałąź `data` (Settings → Branches → Add rule dla `data`: wymagaj
  pull requestów dla ludzi, pozwól obejść tylko botowi Actions), żeby przejęta sesja w przeglądarce nie mogła cicho wypchnąć na nią zmian.
- Runner nie przechowuje długo żyjących sekretów poza własną rejestracją, a jego katalog roboczy należy traktować jak
  jednorazowy: każdy, kto uruchomił na nim kod, mógł zostawić pliki. Preferuj runnery efemeryczne (jedno zadanie), a przy
  stałym czyść `/home/runner/_work` po zadaniach i w razie wątpliwości rejestruj ponownie ze świeżego tokenu.
- Obserwuj oznakę nadużycia runnera: niespodziewane pliki workflowów z `runs-on: [self-hosted, planwat]` albo zmiany
  `refresh.yml` / `.github/actions/refresh`. Alarmuj dla tych ścieżek regułą CODEOWNERS lub wymaganym przeglądem w ochronie gałęzi.

## Wolontariusze

Domowy runner nie jest jedynym źródłem. Zaproszeni wolontariusze uruchamiają ten sam crawler w trybie
`--assign volunteers.json --as <login>` (rejestr z gałęzi `volunteers`, edytowany panelem `tools/volunteer/manage.py`): każdy sprawdza tylko swoją część grup i wypycha paczkę na gałąź `crawl`
własnego forka. Koordynator `collect.yml` (runner GitHub, co 30 min) sprawdza paczki, liczy głosy i przyjęte plany
zapisuje na `data`, a stemple do `volunteer-state.json`. Domowy runner zostaje zaufaną kotwicą: jego wyniki idą na `data`
jak dotąd. Grupy, które wolontariusze właśnie potwierdzili, traktuje jako świeże, a jego sprawdzenie grupy unieważnia
starsze głosy wolontariuszy, więc wolne kworum nie nadpisze planu, który runner właśnie widział. Wolontariusz trzyma
wyuczone tempo i blokady swojego łącza osobno (`--faculty-state`), zamiast korzystać z liczb domowego runnera z
`refresh-state.json`. Całość, łącznie z modelem zaufania:
[WOLONTARIUSZE.md](WOLONTARIUSZE.md).

## Co pokazuje strona

Każda strona grupy pokazuje **Zaktualizowano** (kiedy plan ostatnio się zmienił) i **Sprawdzono** (kiedy crawler ostatnio go
zweryfikował), pobrane w czasie budowy z `refresh-state.json`. Grupy nigdy nieodświeżone pokazują własną datę wygenerowania z
kalendarza.

## Dwa semestry naraz

Wydziały publikują plany nadchodzącego semestru przed jego startem. W sierpniu (semestr zimowy) oraz od stycznia do lutego
(semestr letni) każdy przebieg odświeża więc najpierw trwający semestr, a potem nadchodzący, do jego własnego katalogu
`timetables/<semestr>/` (`core.upcoming_reference`). Nadchodzący semestr jest śledzony w `refresh-state.json` pod kluczem
`<GRUPA>@<semestr>`, więc daty „sprawdzono” i „zmieniono” trwającego semestru pozostają nietknięte. To, czego jeszcze nie
opublikowano, po prostu nie istnieje i nigdy nie sprawia, że przebieg jest niepełny. Kalendarz jest przyjmowany tylko wtedy,
gdy większość jego zajęć mieści się w oknie semestru (`core.term_window`), więc wydział, który wciąż pokazuje plan sprzed roku,
nie zostanie zapisany pod nowym semestrem.

Budowa publikuje każdy znaleziony semestr: strona grupy pokazuje trwający (lub następny) semestr, a gdy grupa ma jeszcze
jeden, przełącznik Zima / Lato (`?t=<semestr>`, kalendarz `plan-<semestr>.ics`).

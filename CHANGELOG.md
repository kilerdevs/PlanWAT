<div align="center">

<img src="src/icons/icon.svg" alt="PlanWAT" width="64" height="64">

# Dziennik zmian

[![Keep a Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-E05735?style=flat)](https://keepachangelog.com/pl/1.1.0/)
[![SemVer](https://img.shields.io/badge/wersjonowanie-SemVer-3F4551?style=flat)](https://semver.org/lang/pl/)
[![Ostatni tag](https://img.shields.io/github/v/tag/kilerdevs/PlanWAT?style=flat&label=ostatni)](https://github.com/kilerdevs/PlanWAT/tags)

</div>

Wszystkie istotne zmiany w PlanWAT są opisane tutaj. Format opiera się na
[Keep a Changelog](https://keepachangelog.com/pl/1.1.0/), a wersjonowanie na SemVer.

## [Unreleased]

## [1.1.1] - 2026-10-22

### Zmieniono
- **Rodzaj zajęć w tytule wydarzenia** (pomysł z [#34](https://github.com/kilerdevs/PlanWAT/pull/34)): w subskrybowanych
  i pobieranych kalendarzach (`plan.ics`, `plan-przypomnienia.ics`, plik z „Kalendarza” i z „Moich przedmiotów”) tytuł to
  „Matematyka I (Wykład)” zamiast „Matematyka I”, więc Google Calendar i iPhone pokazują rodzaj od razu. Dopisek powstaje przy
  budowie z `CATEGORIES`, a pliki w `timetables/` się nie zmieniają. Strona zdejmuje go przy czytaniu, więc kolory, „Moje
  przedmioty”, statystyki i liczniki nadal grupują po przedmiocie. Subskrypcje dostaną nowe tytuły przy najbliższej synchronizacji.

## [1.1.0] - 2026-10-22

### Dodano
- **Comiesięczna aktualizacja mapy kampusu:** workflow `map.yml` pobiera świeże kafelki i resztę mapy, testuje zbudowaną stronę
  (testy budowy i testy przeglądarkowe mapy) i publikuje ją na gałęzi `map`, którą Pages nakłada przed budową. Gałąź ma jeden
  commit, więc historia repozytorium nie rośnie co miesiąc.
- **Mądrzejsza strona 404:** link do grupy wpisany małymi literami (`/wcy26ky3s1/`) prowadzi prosto do grupy, a przy
  literówce strona podsuwa najbliższe kody grup i wyszukiwanie na liście.
- **Sesja egzaminacyjna** na stronie grupy: osobny arkusz z egzaminami i zaliczeniami z planu (filtr rodzaju, licznik dni,
  eksport samych terminów do `.ics` z wybranym przypomnieniem). Bloki „Sesja …” i przerwy nie są już pokazywane jako zajęcia:
  tydzień dostaje czytelny baner z datą, a dzień tylko notkę.
- **Uczciwe statystyki:** godziny dydaktyczne liczone bez rezerwacji sal, przerw, świąt i bloków sesji; te pozycje są pokazane
  osobno, żeby nie zawyżały średniej tygodniowej ani wykresów.
- **Udostępnianie dnia:** arkusz „Udostępnij” z wyborem dnia, podglądem tekstu i obrazu PNG 1080 × 1350; obok niego link do całego
  planu.
- **Szybki wybór w „Wolnych salach”:** „Teraz”, „Po zajęciach” i „Jutro rano” ustawiają datę, godzinę i długość okna jednym dotknięciem.
- **Własne dodatkowe zajęcia:** SKS, konsultacje, projekt — dodawane lokalnie, widoczne tylko w tej przeglądarce, z kontrolą kolizji
  i bez wpływu na oficjalne statystyki, porównania i pobierany plan.
- **Wybór przypomnienia w kalendarzu:** pobierany `.ics` jest generowany w przeglądarce, więc można wybrać brak przypomnienia,
  15 min, 30 min, 1 h albo 1 dzień; subskrypcje zachowują stałe 15 min.
- **Skróty aplikacji:** manifest PWA dostaje skróty „Wszystkie plany” / „Mój plan” i „Mapa kampusu”.
- **Szukanie grupy bez kodu:** na stronie głównej arkusz „Nie znasz kodu grupy?” prowadzi przez wydział i rok naboru do kodu grupy.
- **Mapa:** filtry „Otwarte teraz” i „Dostępne” czytają tagi `opening_hours` i `wheelchair` z OpenStreetMap. Nieznane godziny i brak
  danych o dostępności są pokazywane jako nieznane, wyłączone z filtrów i policzone w nocie pod filtrami.
- **Mapa:** miejsca wokół kampusu jako opisane plakietki: przystanki tramwajowe i autobusowe, akademiki, Domki Radiowa,
  stołówki, bufety, restauracje, bary, sklepy, paczkomaty i parkingi. Panel „Miejsca” przełącza kategorie, wyszukiwarka
  znajduje miejsca, a karta miejsca daje trasę pieszo. Dane w `src/places.js`, odtwarzane przez `tools/places/make_places.py` z
  OpenStreetMap.
- **Mapa:** bogatszy ciemny styl z zielonymi parkami i trawą, niebieską wodą, odcieniami zabudowy i chłodniejszą paletą brył 3D.
- **Przewodnik** po pierwszym otwarciu (telefon i pulpit): przesuwany arkusz z ośmioma krokami (zmiana tygodnia przesunięciem,
  skok z daty, „Gdzie odrobić?”, przycisk „Mapa” i podkreślone sale, porównywanie grup, wolne sale, statystyki, kalendarz, przedmioty i
  aplikacja) i małymi, zapętlonymi animacjami. Pokazuje się raz w przeglądarce, a przycisk „Jak korzystać” (z ikoną `?`) w
  wierszu narzędzi wywołuje go ponownie.
- **Okienka** (przerwy i czas przejścia) także na siatce pulpitu, u dołu zajęć, po których następują.
- **Motyw jasny:** domyślnie według systemu, z przełącznikiem Auto / Ciemny / Jasny na stronie głównej i grupy (zapis tylko
  w przeglądarce; mapa pozostaje ciemna).
- **„Drukuj / PDF”** daje teraz jeden czysty arkusz A4 na tydzień: czarno na białym, jedna linia na zajęcia, bez przycisków ani
  nagłówka i stopki przeglądarki.
- **Aplikacja instalowana:** przycisk „Zainstaluj aplikację” na stronach grup (nie na stronie głównej), gdy przeglądarka
  oferuje instalację (Chrome, Edge, Android), podpowiedź dla Safari na iOS, znaczniki iOS, manifest także na mapie. Testy
  czytają własną kontrolę instalowalności Chromium dla strony głównej, grupy i mapy.
- **„Moje przedmioty”** na stronie grupy: odznacz przedmioty, na które nie chodzisz (przedmioty do wyboru, języki). Znikną z
  widoków, statystyk i pobranego `.ics`. Zapis tylko w przeglądarce, a plik subskrypcji pozostaje pełnym planem.
- **Dwa semestry na grupę:** strona grupy dostaje przełącznik Zima / Lato (`?t=<semestr>`), gdy istnieje drugi semestr, a
  kalendarze drugiego semestru są publikowane jako `plan-<semestr>.ics` (i `plan-<semestr>-przypomnienia.ics`).
- **Odświeżanie:** gdy publikowany jest nadchodzący semestr (sierpień, styczeń–luty), jest odświeżany obok trwającego, z własnym
  stanem, a kalendarze, których zajęcia w większości wypadają poza semestrem, są odrzucane.
- **Odświeżanie obejmuje WCY:** lista grup z menu skoku wydziału, etykieta i daty semestru ustawiane przez sterownik, a strony
  wciąż pokazujące zajęcia poprzedniego semestru są pomijane zamiast trafiać do nowego.
- Strona grupy: gdy wszystkie zajęcia planu poprzedzają semestr (wydział nie opublikował jeszcze nowego planu), widać
  stosowną informację.
- Strona grupy: czas przejścia między zajęciami w różnych budynkach („Do bud. 65 · ~6 min pieszo”, z linkiem do mapy), z
  ostrzeżeniem, gdy jest dłuższy niż przerwa. Karta „Teraz” dolicza go do następnych zajęć.
- **Offline i instalacja:** Service Worker (`/sw.js`, najpierw sieć) zachowuje otwarte strony i plany, strona grupy mówi, kiedy
  pokazuje zapisaną kopię, a manifesty i ikony pozwalają dodać każdą grupę do ekranu głównego.
- **Przypomnienia w kalendarzu:** `<GRUPA>/plan-przypomnienia.ics`, ten sam kalendarz z przypomnieniem 15 minut przed zajęciami,
  włączany przełącznikiem w „Dodaj do kalendarza”.
- **Podstawy publicznej strony:** `/prywatnosc/` (informacja o prywatności i zasady), notka w stopce, że PlanWAT nigdy nie prosi o
  adres e-mail, `robots.txt`, `/.well-known/security.txt` i `build.py --noindex` dla podglądu `dev`.
- Strona grupy: link „Wszystkie grupy” nad nazwą grupy wraca do listy grup.
- Strona grupy: każde zajęcia pokazują, które to spotkanie z przedmiotu i rodzaju w semestrze, np. „Wykład · 3/15” (jednorazowe
  zajęcia bez numeru).
- Strona grupy: dotknięcie zajęć otwiera „Gdzie odrobić?” dla tego konkretnego spotkania (ten sam przedmiot, rodzaj i numer w
  innych grupach rocznika), z linkiem do wszystkich terminów przedmiotu.
- **Mapa kampusu** (`/mapa/`): wszystkie budynki WAT na ciemnej mapie 3D (MapLibre GL JS, kafelki OpenFreeMap), pokolorowane
  według wydziałów, z wyszukiwarką, legendą wydziałów, przełącznikiem 2D/3D, przyciskiem całego kampusu, trasą pieszo i linkami
  `?b=<budynek>`. Wraca do zwykłej listy budynków, gdy mapa nie może się załadować. Sale na stronie grupy prowadzą do budynku, a
  „Mapa” przy dniu otwiera zajęcia i budynki tego dnia (`?g=<GRUPA>&d=<data>`). Tylko ta strona może ładować silnik mapy i
  kafelki, a CSP pozostałych stron się nie zmienia.
- Strona grupy: daty „Zaktualizowano” i „Sprawdzono” z odświeżania oraz zobowiązanie opiekuna, że PlanWAT pozostanie darmowy
  (także w stopce strony głównej).
- **Automatyczne odświeżanie:** zaplanowany workflow ponownie czyta strony planów WLO, WEL i WIM (sterowniki WCY i WTC
  przygotowane, wyłączone), waliduje kalendarze i publikuje je przez gałąź `data`, którą nakłada budowa Pages. Działa wyłącznie
  na własnym runnerze, bo strony wydziałów blokują adresy centrów danych GitHub. Zob. docs/REFRESH.md.
- Strona główna: karty „Teraz w Twoich grupach” (co jest teraz lub zaraz w ulubionych grupach), chipy filtra wydziałów,
  nagłówki roczników, gwiazdki przy każdej grupie, rozwiń/zwiń wszystko, `/` do wyszukiwania, linki `?q=`, przyciski czyszczenia
  i przepisana stopka (nieoficjalny projekt, brak cookies).
- Plany 23 grup WTC (np. `WTC26NX1S1`, `WTC22CO1S0`) skonwertowane z planów Plansoft WTC (`WTC zima 2026/2027`, semestr zimowy 2026/27).
- Strona grupy: widoki listy i miesiąca, przerwy między zajęciami, postęp przedmiotów, statystyki, porównywanie grup (ze
  wspólnym wolnym czasem), „Gdzie odrobić?” (te same zajęcia w innych grupach rocznika), subskrypcja kalendarza (Google, Apple,
  link), udostępnianie, druk / PDF i informacja, że plan zmienił się od ostatniej wizyty. Wszystko za darmo i zapisywane tylko w
  przeglądarce.
- Strona główna: ulubione i ostatnio oglądane grupy. Enter otwiera jedyną pasującą grupę.
- Budowa: `site/data/` (lista grup, rezerwacje sal, zajęcia roczników) dla powyższych narzędzi.
- Plany grup WCY26KY1S1, WCY26KY2S1, WCY26KY4S1, WCY26KY5S1, WCY26KY6S1 i WCY26KYAS1 (semestr zimowy 2026/27). Przy wielu
  grupach strona główna wyświetla listę zamiast przekierowywać.
- Plany 16 kolejnych grup (np. `WCY26_M1`, `WCY26_Fiz1a`, `WCY26IB1bS6`): kody grup mogą zawierać małe litery i podkreślenia, a
  `X-PLAN-GROUP` każdego pliku zgadza się z jego nazwą.
- Strona główna: wyszukiwanie grupy, listy wydziałów domyślnie zwinięte i otwierane przy pasującym wyszukiwaniu.
- Strona grupy: w sobotę i niedzielę bez zaplanowanych zajęć od razu otwiera się następny tydzień.
- Testy przeglądarkowe dla wyboru wydziału, wyszukiwania grup, przejścia przez weekend i skanu dostępności strony głównej,
  a plan WCY26KY3S1 jest przypięty w `tests/fixtures/wcy26ky3s1.plan.json` zamiast w pierwszym eksporcie.
- Podgląd `dev`: każde wdrożenie Pages publikuje szczyt `dev` pod `/dev/`, z wzajemnymi linkami do produkcji.
- Dokumentacja: cała dokumentacja Markdown przepisana na polski, z diagramami, wykresami i plakietkami.

- **Wolne sale** wróciły w nowym wydaniu: wybierasz dzień, godzinę, czas, którego potrzebujesz (od 30 min do 3 h), budynek
  i numer sali, a każda sala dostaje pasek dnia z zajęciami (czerwone) i wolnym oknem (zielone). „Pokaż też sale wolne
  później” dopisuje sale, które zwolnią się w ciągu dnia, a nazwa budynku prowadzi na mapę. Sale bez zajęć w pobliżu
  danego dnia są pominięte i policzone zamiast zgadywane. Dane z `data/rooms.json` pochodzą z planów wszystkich grup.
- **Narzędzia w trzech zakładkach** zamiast jednego rzędu dwunastu przycisków: Plan (ulubione, moje przedmioty, jak korzystać,
  instalacja), Eksport (pobranie, kalendarz, udostępnianie, drukowanie) i Analiza (statystyki, porównanie grup, wolne sale,
  mapa planów). Strzałki, Home i End przechodzą między zakładkami, a ostatnia użyta zakładka jest zapamiętana na urządzeniu.
- **Mapa planów** (przycisk w narzędziach, zakładka Analiza) ma cztery zakładki: Twój plan (współczynnik z podziałką, archetyp,
  Twój tydzień na tle typowego, to, co wyróżnia plan, z Twoją wartością i średnią), Mapa (kropki, numerowana lista archetypów
  z definicją i typowym tygodniem, dotknięcie archetypu zostawia na mapie tylko jego plany), Podobne (czym inny plan różni się
  od Twojego) i Metoda (definicja każdej z 13 cech z wagą, tabela archetypów, opis mapy). „Współczynnik przejebania™” to liczba od 0 do 100: jaka część porównanych planów jest lżejsza od Twojego (godziny, okienka, długość dni, wczesne starty, weekendy, zmiany budynków). Liczone przy każdej budowie z planów opublikowanych przez wydziały (`profiles.py`: PCA i k-średnie, bez uczenia modeli) i zapisane w `data/profiles.json`.
- **Prywatność:** tabela „PlanWAT kontra serwis z logowaniem kodem” z README także na stronie `/prywatnosc/`.
- **Aktualizacja planów** co 2 godziny zamiast raz na dobę, a strona jest odbudowywana zaraz po zakończeniu przebiegu.
- **Wychowanie fizyczne** ma salę: Ośrodek Szkoleniowo-Sportowy WAT, także jako punkt na mapie.
- **Odświeżanie:** zgłoszenia blokad z crawla do proxy wyjściowego (`POST /api/block`): proxy wycofuje wyjście puli, które
  przewiozło stronę blokady, a lista `EGRESS_DIRECT_FACULTY` prowadzi wybrane wydziały linią domową — jedno oznaczone wyjście
  nie psuje już całego wydziału (zob. docs/EGRESS.md).
- **Egress:** panel monitoringu w stylu serwisu (te same tokeny, ciemny i jasny motyw z przełącznikiem Auto / Ciemny / Jasny,
  odświeżanie bez przeładowania) z kartą postępu odświeżania na żywo: pasek, licznik sprawdzonych grup, tempo, przewidywany
  koniec i wiersz stanu każdego wydziału (w kolejce, sprawdza, czeka na odblokowanie, brak postępu, gotowe). Crawler raportuje
  postęp najlepszym wysiłkiem (`PLANWAT_EGRESS_PROGRESS`, `POST /api/progress`), a egress liczy ETA z własnych pomiarów tempa
  i mówi „wstrzymane”, gdy wydział czeka na odblokowanie — zgubione zdarzenie psuje tylko dokładność, nigdy crawl.
- **Egress:** karta postępu odlicza do następnego odświeżenia („następny ≈ 16:23 (za 1 h 59 min)”, także w trakcie przebiegu),
  a kliknięcie wiersza przebiegu rozwija jego szczegóły: profil, czasy, kod wyjścia i tabelę wydziałów ze sprawdzonymi, zmianami,
  pominiętymi, stanem (zablokowany, zdegradowany, nadchodzący) i czasem oczekiwania na odblokowanie.
- **Ukrywanie części przedmiotu** ([#31](https://github.com/kilerdevs/PlanWAT/issues/31)): w „Moich przedmiotach” przedmiot
  prowadzony w kilku formach rozwija się strzałką na wykłady, ćwiczenia, laboratoria itd. Każdą z nich można odznaczyć osobno,
  np. przy zwolnieniu z ćwiczeń. Ukryte zajęcia znikają z widoków, statystyk, pobranego pliku .ics i dnia na mapie kampusu,
  a wcześniej zapisane wybory całych przedmiotów działają jak dotąd.

### Zmieniono
- **Mapa kampusu w całości z samej strony:** silnik MapLibre GL JS (te same bajty co wcześniej, sprawdzane tą samą sumą SRI), styl
  OpenFreeMap `dark`, wektorowe kafelki, glify etykiet i ikony leżą w `src/map/` i są publikowane pod `mapa/`. Kafelki obejmują
  każdy widok, na jaki mapa pozwala (także przechylenie do 60° przy granicy kampusu), co wylicza sam MapLibre
  (`tools/map/coverage.js`); `tools/map/vendor_map.py` odświeża całość. CSP żadnej strony nie wymienia już innego serwera.
- **Krój Inter z samej strony** zamiast z Google Fonts: żadna strona poza mapą nie łączy się już z cudzym serwerem, CSP
  zezwala tylko na `font-src 'self'`, a przeglądarka pobiera tylko te podzbiory, którymi faktycznie rysuje (urządzenia Apple
  używają SF Pro i nie pobierają nic).
- **Obraz do udostępniania mówi więcej:** karta PNG (1080 × 1350) mieści teraz całe nazwy zajęć i sale (zawija zamiast ucinać),
  rodzaj i numer spotkania, datę wygenerowania planu, wydział, semestr i numer tygodnia. Doszły kafelki podsumowania (liczba zajęć,
  pierwsze i ostatnie zajęcia, czas w planie, okienka), etykiety okienek z czasem dojścia między budynkami oraz pasek całego tygodnia
  z liczbą zajęć każdego dnia i wyróżnionym wybranym dniem. Stopka podaje adres strony, z której pochodzi plan.
- **Wykres pokrycia wydziałów już się nie zestarzeje:** `build.py` rysuje `pokrycie-wydzialow.svg` przy każdej budowie
  z tych samych grup, które publikuje, a README pokazuje plik z wdrożonej strony zamiast kopii w repozytorium. Ręcznie
  robiony `docs/diagrams/pokrycie-wydzialow.svg` i kolumna liczb w tabeli wydziałów znikają — liczby widać na wykresie.
- **Strony dzielą wspólne style i skrypty:** to, co dotąd każda strona niosła w swoim HTML-u, build zapisuje raz w plikach
  `assets/` o nazwie z haszu treści; znacznik wczytuje je z sumą `integrity`, a bloki zostające w HTML nadal działają
  wyłącznie z hashy CSP. Przeglądarka i Service Worker biorą je raz na wydanie, a całe wdrożenie repozytoryjnego zestawu
  schudło z ~157 MB do ~55 MB — offline działa jak dotąd.
- **CI w dwóch prędkościach:** push na `dev` uruchamia tylko szybkie konteksty (testy jednostkowe i budowa). Matryca
  przeglądarek i skan obrazu Dockera odpalają się wyłącznie w przeglądzie wydania `dev → master`, gdzie wymagane konteksty
  ochrony gałęzi `master` i tak ich szukają — ten sam commit nie jest już badany dwa razy za jednym pushem. Każdy przypadek
  dostaje limit czasu, żeby zawieszony test nie pochłaniał godzin. Konteksty przeglądarkowe czytają przeglądarki Playwright
  z pamięci podręcznej (pliki pobierane raz na podbicie zależności, nie raz na przebieg) i biegną na czterech wątkach
  runnera GitHub (4 vCPU), który domyślnie zostawiał połowę rdzeni bezczynnymi. Audyt zależności developerskich wykonuje się
  raz na przebieg (w testach jednostkowych), nie osobno w każdej przeglądarce.
- `SAST` (CodeQL) nie odpala się już po pushu: kod pokrywają przeglądy wydania i poniedziałkowy przebieg zaplanowany,
  a CodeQL z pusha powielał tylko wynik przeglądu wydania.
- **Pages** pomija budowę i wdrożenie po cichym przebiegu odświeżania: przebieg bez nowych kalendarzy nie zmienia strony,
  więc identyczne wdrożenie nic nie dodaje, a zaplanowana codzienna przebudowa i tak dogoni przełomy semestru. Bramka czyta
  plik wyniku, który przebieg odświeżania wysyła jako artefakt.
- Skany dostępności (axe) w testach czekają na koniec animacji wejścia: Firefox i WebKit potrafiły skanować sekcję jeszcze
  w połowie pojawiania się — jej wtedy półprzezroczyste kolory czytane były jako niski kontrast, co dawało fałszywe
  czerwone w CI. Skany teraz emulują `prefers-reduced-motion` i czekają, aż animacje przestaną biegać — jak robiły to już
  skany arkusza grupy.
- **Odświeżanie rozciąga przerwy cichym grupom:** każdy zakończony check z tym samym planem (również `304`) podwaja przerwę
  tej grupy przed następnym sprawdzeniem, do sufitu `--adaptive-hours` (w akcji 4 h), więc spokojny semestr kosztuje mniej
  więcej połowę zapytań do Incapsuli. Zmiana planu zeruje przerwę i grupa wraca na pełne tempo natychmiast.
- **Obraz self-hosted kompresuje mocniej:** `gzip_comp_level 5` i `gzip_vary on` zamiast poziomu 1 z domyślnym.
- **Strony dla studentów:** spokojniejsze wejście (nagłówek, wyszukiwarka i karty wydziałów na stronie głównej; panel mapy i
  znaczniki budynków na mapie; nagłówek 404 i prywatności) — jedna krótka animacja, wyłączona przy `prefers-reduced-motion`.
  Strona 404 jest wyśrodkowana, ma ikonę kalendarza i dwa wyjścia (lista planów, mapa kampusu). Wiersze przewijane w bok
  (filtry wydziałów, narzędzia planu, budynki w „Wolnych salach”) bledną na uciętej krawędzi, dopóki jest co przesunąć, a tabela
  porównawcza na telefonie dostaje podpis „Przesuń tabelę w bok” (strona prywatności nadal nie ma ani linijki JavaScriptu).
- **Plan:** ✓ przy każdych skończonych zajęciach, nie tylko dzisiejszych.
- **Mapa:** w widoku dnia pozostałe budynki cofają się, karta budynku jest zwarta, więc dotknięte zajęcia zostają widoczne,
  zwinięcie arkusza ponownie ustawia mapę, dotknięcie mapy zamyka legendę, a podpowiedź wyszukiwarki nie jest już ucięta w
  połowie litery.
- Testy podążają za grupami w `timetables/` zamiast zakładać jedną: każda grupa musi dostać stronę i kalendarz bajt w bajt, a
  każda strona grupy musi renderować się w przeglądarce bez błędów i naruszeń CSP. Przekierowanie dla pojedynczej grupy pokrywa
  syntetyczny test budowy.
- **Odświeżanie:** szybsze i szersze: przerwy 1,5–4 s, próg świeżości 60 minut, sześć torów (wszystkie polityki Incapsula
  naraz), a odpowiedź blokady jest ponawiana na świeżym połączeniu (`--block-retries`, domyślnie 2) zamiast od razu kończyć
  wydział; pula rotuje wyjścia w obrębie warstwy zweryfikowanej.
- **Odświeżanie:** strony WCY z planem innego semestru (albo pustą siatką) liczą się jako jeszcze nieopublikowane, bez
  oznaczania przebiegu jako pogorszony.
- `CI`, `Egress` i `SAST` nie uruchamiają się już po pushu na `master`: pull request wydania zdążył je wykonać.
- **Egress:** karta bezczynnego postępu mówi jedno: chip „bez przebiegu” plus wiersz harmonogramu z odliczaniem (zdublowane
  „brak aktywnego przebiegu” zniknęło), kolumna czasu w szczegółach przebiegu nazywa się „kiedy” zamiast „o”, a liczebniki
  odmieniają się po polsku: „1 sprawdzony”, „72 pominięte”, „2 próby”.
- **Płynniejsze animacje na wszystkich stronach:**
  - zaznaczenie w przełącznikach (widok, narzędzia, mapa planów) przesuwa się;
  - miesiące przewijają się jak tygodnie;
  - zmiana widoku, otwierane panele, powiadomienia i pola formularzy łagodnie się pojawiają;
  - wykresy w statystykach rosną od osi;
  - zmiana motywu przechodzi płynnie;
  - na stronie głównej wydziały zwijają się płynnie, a wyszukiwarka grup także się chowa z animacją.

  Przyciski reagują na dotyk, a ruch ustępuje całkowicie przy „ogranicz ruch” w systemie.

### Naprawiono
- **Kontrast w jasnym motywie:** daty minionych dni, opis dnia w kolumnie „Dziś” i plakietka „Dziś” miały kontrast 4,0–4,4:1,
  a zielona godzina w „Wolnych salach” 3,7:1, zamiast wymaganych 4,5:1. Odcienie `--past-2`, `--t3`, `--accent-text` i `--free`
  są odrobinę ciemniejsze, a wynik na mapie planów (szary w środku skali, 2,8:1) przybiera w jasnym motywie odcień tekstu. Skan axe wcześniej tych miejsc nie oceniał.
- **Postęp semestru liczony z pustych miesięcy:** 31 kalendarzy WCY (np. `WCY25IX1S0`) miało daty zeszłego semestru letniego
  (np. 02.03–27.07.2026), bo konwerter brał początek semestru z pozostawionych na stronie wydziału zajęć z marca. Siatka tygodni
  zaczynała się wtedy w marcu, a „Postęp semestru” pokazywał 69% zamiast 15%. `build.py` sprawdza teraz początek semestru
  każdego kalendarza: gdy nie należy do jego semestru (albo koniec wypada przed początkiem), kalendarz dostaje daty, na które
  zgadzają się pozostałe kalendarze tego wydziału, a bez nich daty wynikające z samych zajęć albo całe okno semestru. Koniec
  nigdy nie wypada przed ostatnimi zajęciami grupy, a poprawne daty (także koniec w marcu przy późniejszym starcie) zostają bez
  zmian. Zabłąkane zajęcia z innego semestru nie przesuwają już początku semestru, a sterownik WCY liczy go tylko z zajęć
  tego semestru.
- **Strona prywatności wymienia wszystko, co zostaje w przeglądarce:** doszły motyw, zakładka narzędzi, przewodnik, ukryte
  przedmioty i własne zajęcia. Test pilnuje, żeby każde nowe ustawienie zapisywane w `localStorage` trafiło na tę listę.
- **Odstępy w arkuszach:** wiersz szybkich wyborów nie klei się już do pola powyżej (data w „Udostępnij”), przycisk pobierania
  `.ics` ma powietrze po wyborze przypomnienia, a lista „Podobne plany” nie dotyka rzędu filtrów na mapie. Reguły są punktowe,
  więc inne arkusze zachowują dotychczasowy rytm.
- **Rezerwacje:** bloki zarezerwowanych godzin nie pokazują już samotnego „-” ani licznika spotkań („Rezerwacja · 22/114”);
  w planie, pasku „teraz / następne”, porównaniu i zmianach widnieją jako „Rezerwacja”, nie otwierają „Gdzie odrobić?” i nie
  trafiają do legendy, postępu przedmiotów, liczby przedmiotów w statystykach ani „Moich przedmiotów”.
- **Sale:** kody z ukośnikiem są zapisywane bez spacji (`54/ 62` → `54/62`, `29/ 54 30/ 54` → `29/54 30/54`) w planie,
  na stronie głównej i w porównaniu.
- **Strona grupy:** przewijany nagłówek nie wjeżdża już na przyciski narzędzi i przełącznik widoku (skaluje się do dolnej
  krawędzi zamiast przesuwać w dół), etykiety słupków w statystykach nie łamią słów w środku („międzysemestraln / a”), wiersz
  „Dodaj grupę” w porównaniu mieści się na 360 px, a stopka nie zostawia podwójnego odstępu na unoszący się przycisk tygodnia.
- **Egress:** panel monitoringu znów mieści swoje dane: nagłówki kart się nie łamią, tabela wydziałów nie ucina ostatnich kolumn
  (sztywny układ, liczby do prawej), wartości kafelków się nie zawijają (opóźnienia w sekundach, np. `5,7 s`), a raport bez kodu
  wyjścia czyta się jako „nieznany” zamiast „undefined”. Godziny raportów są w końcu lokalne (były w UTC czytanym jak lokalny),
  tabela wychodów ma kolumnę „pudła” (nieudane próby), przyklejony nagłówek i podpowiedź z ostatnim sprawdzeniem, a nowa karta
  Egress pokazuje obsłużone żądania proxy, tunele w toku, odmowy i czas działania kontenera.
- **Odświeżanie WTC:** indeks wydziału jest znów czytany poprawnie (płaski `/Plany/index.xml` w miejsce nieistniejącego
  `Plany/<semestr>/index.xml`), a PDF-y są plikowane tylko wtedy, gdy indeks nazywa odświeżany semestr — plany WTC są w końcu
  odświeżane automatycznie.
- **Odświeżanie WCY:** nowy kalendarz jest porównywany ze starym po przycięciu starego do odświeżanego semestru — plik zasiany
  13.10 niósł jeszcze lekcje poprzedniego lata, więc jego oczyszczenie (np. 621 → 309 wydarzeń) było odrzucane jako podejrzanie
  urwany plan; teraz WCY publikuje właściwe, jednosemestralne kalendarze i nie degraduje przebiegu.
- **Odświeżanie:** raporty przebiegu znów docierają do GUI proxy (proxy odpowiadało na nie 403, bo szły przez nie samo); raport
  leci teraz połączeniem omijającym proxy, przez sieć wewnętrzną.
- **Odświeżanie:** wydział, któremu nie udało się wylistować grup (np. chwilowa awaria proxy egress w trakcie przebiegu), nie
  przepisuje już do raportu zeszłego wpisu — dostaje świeży wpis z przyczyną `listing` i flagą zdegradowany, więc panel i
  zgłoszenie mówią, co naprawdę się stało, a stara degradacja nie ciągnie się przez kolejne przebiegi.
- **Egress:** panel nie przelewa się na wąskich ekranach: wiersze przebiegów układają się w bloki, a szczegóły przewijają się
  poziomo w swojej własnej tabeli (zamiast rozsypywać kolumny i wypychać kartę poza ekran), tabela wydziałów i pula chowają
  najmniej istotne kolumny („obejścia”, „źródło”), a kafelki nie przycinają etykiet (np. „odrzuconych”). Panel znosi też
  powiększoną czcionkę przeglądarki: nagłówki kolumn liczb mają zapas (w najgorszym razie kończą się wielokropkiem zamiast
  nachodzić na siebie), długie etykiety kafelków dzielą się z myślnikiem, a licznik nowych wychodów przeniósł się do nagłówka
  karty puli.
- **Prywatność:** aliasy prowadzących (inicjał i nazwisko sklejone w polu sali, np. `AKowalski`) nie trafiają już do planów.
  Konwerter je odrzuca, `build.py` odmawia zbudowania kalendarza z takim polem, a `tools/scrub_staff.py` czyści już opublikowane.
- **iPhone:** przyciski nad planem są zwarte zamiast dużych owali, „Zainstaluj aplikację” pokazuje kroki dodania do
  ekranu początkowego, a arkusz szczegółów na mapie da się przewijać do ostatnich zajęć.
- **Crawler:** wydziały za różnymi politykami Incapsula są przeglądane równolegle, stan zapisuje się co 25 sprawdzeń także
  przy odpowiedziach 304, a zapis stanu jest bezpieczny przy pracy wielu torów.
- **Dane kadry w `LOCATION`:** przy części komórek WLO konwerter wpisywał do pola sali także prowadzących (np. `dr inż. …, 255 S`),
  przez co 8 kalendarzy publikowało nazwiska. Konwerter odrzuca teraz każdą część sali będącą tytułem z nazwiskiem, a build odmawia
  kalendarza, w którego `LOCATION` taka część występuje. Gałąź `data` została oczyszczona wraz z historią.
- Niewidoczny przycisk instalacji pojawiał się na iOS, mimo że miał być ukryty (reguła CSS nadpisywała atrybut `hidden`).
- Alerty CodeQL: nazwa pliku semestru powstaje z zweryfikowanej wartości zapytania, a nie z tekstu strony. Wyrażenie regularne w
  teście przestało pomijać znaczniki pisane wielkimi literami. Zamiana średnika w teście nie jest już tożsamościowa.

### Usunięto
- **Wszystkie dane osobowe kadry:** nazwiska, imiona i tytuły naukowe zniknęły z kalendarzy, strony, konwerterów, testów i całej
  historii Gita. Kalendarze nie zawierają już linii `CONTACT` ani prowadzącego, a build odrzuca każdy kalendarz, który je ma.

## [1.0.0] - 2026-10-11

Pierwsze publiczne wydanie.

### Dodano
- Strona planu grupy: karta „Teraz” dla trwających lub następnych zajęć (sala, godziny, postęp), pogrupowane listy dni na
  telefonach i siatka dzień × godzina na szerokich ekranach, arkusz wyboru tygodnia, nawigacja strzałkami, przesunięciem i
  klawiaturą, pastylka „Bieżący tydzień”, legenda przedmiotów, przewijanie telefonu do bieżących zajęć i pobieranie `.ics`.
- Plany jako pliki iCalendar w `timetables/<semestr>/<GRUPA>.ics`, czytane w przeglądarce przez `src/ics.js` (składane linie,
  escapowanie, czas lokalny i UTC, powtarzanie tygodniowe i dzienne, wykluczone daty, pominięte zdarzenia odwołane i całodniowe).
- `build.py`: jedna strona na grupę pod `/<GRUPA>/` z bieżącym semestrem (wybieranym po dacie), lista grup w katalogu głównym,
  przekierowująca przy jednej grupie, strona 404 i Content-Security-Policy z hashami na każdej stronie.
- Wdrożenie GitHub Pages po każdym pushu na `master` i codziennie, więc nowy semestr startuje pierwszego dnia.
- Samodzielnie hostowany obraz Docker: dwuetapowa budowa, nginx bez uprawnień i tylko do odczytu, nagłówki bezpieczeństwa i CSP
  w nagłówku generowane ze zbudowanych stron.
- CI: testy czytnika kalendarza z progami pokrycia, testy budowy, testy przeglądarkowe Playwright (Chromium, Firefox, WebKit;
  pulpit i telefon) ze skanem WCAG axe, skan obrazu Docker (Grype) i test dymny, CodeQL oraz Dependabot.

[Unreleased]: https://github.com/kilerdevs/PlanWAT/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/kilerdevs/PlanWAT/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/kilerdevs/PlanWAT/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/kilerdevs/PlanWAT/releases/tag/v1.0.0

---
name: Plan zajęć WCY26KY3S1
description: Ciemny, telefonowy plan zajęć dla grup WAT w idiomie ciemnego trybu iOS.
colors:
  accent: "#0a84ff"
  accent-text: "#4da3ff"
  ground: "#000000"
  surface-1: "#111113"
  surface-2: "#1c1c1e"
  surface-2-hover: "#232326"
  surface-3: "#2c2c2e"
  surface-4: "#3a3a3c"
  label: "#f5f5f7"
  label-secondary: "#a1a1a6"
  label-tertiary: "#86868b"
  label-quaternary: "#6e6e73"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "4rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.04em"
  display-compact:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.22
    letterSpacing: "-0.02em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.28
    letterSpacing: "-0.012em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.3
    fontFeature: "\"tnum\""
rounded:
  control: "12px"
  card: "16px"
  group: "20px"
  sheet: "24px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  2xl: "32px"
  3xl: "48px"
  4xl: "64px"
components:
  button-round:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.label}"
    rounded: "{rounded.pill}"
    size: "44px"
  button-round-hover:
    backgroundColor: "{colors.surface-3}"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.label-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "6px 14px 6px 12px"
  chip-hover:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.label}"
  list-group:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.group}"
  lesson-row:
    textColor: "{colors.label}"
    typography: "{typography.title}"
    padding: "14px 16px"
  lesson-tile:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.card}"
    padding: "14px 16px 16px 14px"
  lesson-tile-hover:
    backgroundColor: "{colors.surface-2-hover}"
  live-card:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.group}"
    padding: "16px 24px 16px 16px"
  floating-pill:
    textColor: "{colors.label}"
    rounded: "{rounded.pill}"
    height: "48px"
    padding: "0 20px 0 16px"
  sheet:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.sheet}"
---

<div align="center">

<img src="src/icons/icon.svg" alt="PlanWAT" width="64" height="64">

# System wizualny: PlanWAT

**„Apple, ale ciemny”: spokojny, precyzyjny, z jednym akcentem.**

[![Ciemny motyw](https://img.shields.io/badge/motyw-ciemny%20referencyjny-000?style=flat)](#kolory)
[![Jasny motyw](https://img.shields.io/badge/motyw-jasny%20wspierany-f2f2f7?style=flat&labelColor=555)](#motyw-jasny-i-druk)
[![Akcent](https://img.shields.io/badge/akcent-%230a84ff-0a84ff?style=flat)](#kolory)
[![Dotyk](https://img.shields.io/badge/cele%20dotyku-44%20px-blue?style=flat)](#układ)
[![Ruch](https://img.shields.io/badge/ruch-transform%20%2B%20opacity-blue?style=flat)](#cienie-i-głębia)

</div>

---

## Przegląd

**Przewodnia idea: „Kieszonkowa aktywność na żywo” (The Pocket Live Activity)**

Plan zajęć zachowuje się jak coś, co mogłoby wyjść spod ręki iOS: czarne tło, szarości jaśniejsze w miarę zbliżania się
powierzchni, jeden niebieski, który znaczy „teraz / dziś / tu jesteś”, i systemowa typografia, ciasna i pewna. Stronę
czyta się w pośpiechu, na telefonie, między budynkami, więc każda powierzchnia odpowiada na *co, kiedy, gdzie*, zanim
cokolwiek powie o sobie.

Gęstość jest spokojna, nie rzadka. Na telefonach każdy dzień to wcięta, zgrupowana lista (jeden zaokrąglony pojemnik,
wiersze oddzielone wciętymi liniami), a na pulpicie te same wiersze stają się kafelkami w prawdziwej siatce dzień × blok, więc
cały tydzień mieści się na jednym ekranie. Zapamiętywalny motyw to **kapsuła przedmiotu**: czteropikselowy pasek koloru, który
nazywa przedmiot, a dla trwających zajęć wypełnia się od góry do dołu wraz z upływem czasu, w wierszach i na karcie „Teraz”.

Ruch jest fizyczny i krótki: wejścia z łagodnym wyhamowaniem (expo-out), sprężyny przy dotyku i na pływającej pastylce,
View Transitions przesuwające tydzień w bok zgodnie z kierunkiem ruchu oraz dolny arkusz jadący po krzywej arkusza iOS. Ruch
jest zarezerwowany dla zmian stanu, a w pętli kręci się tylko kropka zajęć trwających teraz.

**Najważniejsze cechy:**
- Czarne tło. Głębia pochodzi z jasności powierzchni i sześcioprocentowej krawędzi światła u góry, a nie z cieni.
- Jeden akcent, używany wyłącznie dla „teraz”, „dziś”, fokusu i zaznaczenia.
- Systemowy SF / Inter, zdania zaczynane wielką literą, cyfry tabelaryczne; bez kroju o stałej szerokości, bez etykiet kapitalikami.
- Kolor przedmiotu żyje tylko w kapsule i kropkach legendy.
- Matowe szkło tylko tam, gdzie coś unosi się nad treścią: przyklejony pasek tygodnia i pastylka „Bieżący tydzień”.

## Kolory

Prawie monochromatyczna, ciemna rampa z jednym akcentem systemBlue. Kolory przedmiotów pochodzą z danych planu i są
ograniczone do małych oznaczeń.

### Główne
- **System Blue** (`accent`): sygnał „teraz / dziś”. Kropka na żywo, obwódka stanu „Teraz”, obrys dzisiejszej kolumny,
  pierścienie fokusu, ✓ wybranego tygodnia, wypełnienie postępu semestru.
- **Link Blue** (`accent-text`): ten sam odcień rozjaśniony do tekstu na ciemnych powierzchniach („Teraz · do 11:25”, „Dziś”,
  „Bieżący tydzień”), z kontrastem ≥ 4,5:1.

### Neutralne
- **Czarne tło** (`ground`): strona.
- **Podniesione szarości 1–4** (`surface-1` … `surface-4`): szkielety i rezerwy (1), karty, grupy i arkusz (2), wciśnięte i
  drugorzędne kontrolki (3), uchwyty i najechanie na małe kontrolki (4). `surface-2-hover` to podniesienie kafelków i karty
  „Teraz” po najechaniu.
- **Rampa etykiet** (`label`, `label-secondary`, `label-tertiary`): tekst główny, pomocniczy (daty, rodzaje, meta) i cichy
  (liczniki, podpowiedzi). `label-quaternary` jest tylko do elementów wyłączonych lub dekoracyjnych, bo nie spełnia AA dla
  małego tekstu.
- **Cienka linia** (`rgba(255,255,255,0.08)`, mocniejsza `0.14`): separatory i obrysy. **Krawędź światła**
  (`inset 0 1px 0 rgba(255,255,255,0.06)`): górny połysk każdej podniesionej powierzchni.
- **Odcienie akcentu**: `rgba(10,132,255,0.14)` miękkie wypełnienie (pastylka „dziś”), `0.5` pierścień (wiersz „teraz” i obrys
  karty), `0.35` pierścień i `0.05` poświata (dzisiejsza kolumna na pulpicie), `0.24` błysk (podświetlenie po skoku do zajęć),
  `0.45` zaznaczenie tekstu.

### Nazwane reguły
**Reguła jednego niebieskiego.** Niebieski znaczy „teraz, dziś albo fokus” i nic więcej. Nigdy do dekoracji, nagłówków ani
stanów nieaktywnych.

**Reguła kapsuły.** Kolor przedmiotu pojawia się wyłącznie jako czteropikselowa kapsuła i dziesięciopikselowa kropka legendy.
Nigdy nie barwimy nim tekstu, tła kart ani obramowań.

**Reguła przygasającej przeszłości.** Minione dni i skończone zajęcia schodzą o jeden poziom w tokenach tekstu (label → secondary,
secondary → tertiary), a ich kapsuła przygasa do 45%. Nigdy nie schodzą poniżej `label-tertiary`, więc pozostają czytelne zgodnie z AA.

## Typografia

**Krój nagłówkowy:** SF Pro Display (potem Inter, potem system-ui)
**Krój tekstu:** SF Pro Text (potem Inter, potem system-ui)

**Charakter:** jedna rodzina robiąca całą robotę, po apple'owsku: ciężkie, ciasno wyrównane duże tytuły nad małym,
wygodnym tekstem. Hierarchię niesie kontrast grubości (400/500/600/700), a nie dodatkowe kroje.

### Hierarchia
- **Display** (700, 4 rem pulpit / 2,5 rem telefon, 1,04, −0,04 em / −0,035 em): wyłącznie kod grupy.
- **Nagłówek** (600, 1,25 rem, −0,02 em): nazwy dni na liście telefonu, przedmiot na karcie „Teraz”, etykieta tygodnia od
  tabletu w górę, tytuł arkusza.
- **Tytuł** (600, 1,0625 rem, −0,012 em): nazwy przedmiotów w wierszach, etykieta tygodnia na telefonie, podsumowanie legendy,
  etykiety tygodni w arkuszu. Kafelki schodzą do 0,9375 rem.
- **Tekst** (400, 0,9375 rem, 1,45): daty, szczegóły karty „Teraz”, komunikat pustego tygodnia.
- **Etykieta** (500/600, 0,8125 rem, tabelaryczna): godziny, sale, liczniki, wiersze stanu, chipy, meta. 0,75 rem tylko dla
  czasu trwania i klawiszy.

### Nazwane reguły
**Reguła cyfr tabelarycznych.** Każda godzina, data, licznik i sala jest składana cyframi tabelarycznymi, żeby kolumny godzin
się wyrównywały.

**Reguła zdań.** Żadnych etykiet kapitalikami ani nadtytułów. Wiersze stanu czyta się jak zdania („Następne · za 25 min”).

## Układ

Najpierw telefon, siatka 8 px (półkroki 4 px). Treść w wyśrodkowanej kolumnie `max-width: 720px` z marginesami
`max(16px, safe-area)` na telefonie i `max(32px, safe-area)` od 768 px. Przy 1080 px kolumna rozszerza się do 1240 px, a tydzień
zamienia się w siatkę równych kolumn dni (sobota, w obu układach, tylko jeśli w którymś tygodniu semestru są zajęcia), z jednym
wierszem na każdą odrębną godzinę rozpoczęcia, więc bloki układają się w jednej linii między dniami, a puste miejsca zostają
puste. Nagłówek to jedna kolumna na telefonie i rozdziela tytuł od karty „Teraz” od 1080 px. Punkty przełamania: 370 px
(zwarte wiersze), 768 px (tablet: większy tytuł, etykieta tygodnia z lewej, strzałki z prawej, wyśrodkowany arkusz), 1080 px
(siatka planu). Cele dotyku mają co najmniej 44 px na wskaźnikach dotykowych, a pływająca pastylka i stopka podpowiedzi
szanują dolny obszar bezpieczny.

## Cienie i głębia

Głębia jest tonalna. Powierzchnie wznoszą się przez `surface-1 → surface-4` z sześcioprocentową krawędzią światła u góry, a
obrysy to cienkie linie. Jedyne cienie to miękka czerń pod pływającą pastylką (`0 16px 40px -12px rgba(0,0,0,0.8)`) i pod
arkuszem, bo te elementy naprawdę się unoszą. Szkło (`rgba(22,22,24,0.72)` + `saturate(180%) blur(20px)`) pojawia się
wyłącznie na przyklejonym pasku tygodnia i pływającej pastylce, a gdy przezroczystość jest ograniczona lub nieobsługiwana,
staje się nieprzezroczyste.

### Nazwane reguły
**Reguła braku poświaty.** Żadnych kolorowych ani zerowo przesuniętych cieni-aureoli. Stan pokazuje jednopikselowy pierścień
akcentu i barwione wypełnienie, nigdy poświata.

**Reguła szkła tylko w locie.** Rozmycie tła jest dozwolone wyłącznie na elementach unoszących się nad przewijaną treścią.
Gdy pasek spoczywa na miejscu, rozmycie jest wyłączone.

## Kształty

Ciągłe, iOS-owe zaokrąglenia skalowane do obiektu: 12 px kontrolki, 16 px kafelki, 20 px grupy i karta „Teraz”, 24 px arkusz,
pełne pastylki dla chipów, znaczników „dziś” i pływającej pastylki, koła dla przycisków-ikon. Kapsuła to pasek 4 px z
promieniem 2 px. Ikony to liniowe ikony Lucide o grubości 1,5 (2 przy 14–16 px), rysowane jako inline SVG.

## Komponenty

### Przyciski
- **Kształt:** koła 44 px dla poprzedni / następny (`rounded.pill`), koło 32 px z polem trafienia 44 px dla zamknięcia arkusza.
- **Domyślnie:** `surface-2` z krawędzią światła, ikona w `label`.
- **Najechanie / wciśnięcie / wyłączony:** `surface-3` przy najechaniu (tylko precyzyjne wskaźniki), wciśnięcie skaluje do 0,94
  na sprężynie, wyłączony spada do 32% krycia.
- **Fokus:** dwupikselowy obrys akcentu osiadający z odsunięcia 6 px do 2 px.
- **Drugorzędna pastylka (link pobierania):** pastylka `surface-2` z krawędzią światła, etykieta 13 px półgruba w `label`,
  ikona 18 px w `label-secondary`, wysokość 36 px (44 px na dotyku), `surface-3` przy najechaniu, wciśnięcie 0,97. Celowo
  neutralna: akcent zostaje zarezerwowany dla „teraz / dziś / fokus”.

### Chipy
- **Styl:** pastylka `surface-2`, tekst w `label-secondary`, kropka przedmiotu 10 px.
- **Stan:** wciśnięty wypełnia się 22% koloru przedmiotu plus wewnętrznym pierścieniem w tym kolorze, a kropka rośnie do 1,3.

### Karty i pojemniki
- **Zaokrąglenie:** 20 px grupy, 16 px kafelki.
- **Tło:** `surface-2`. Dzisiejsza grupa dostaje jednopikselowy pierścień akcentu, a wiersz trwających zajęć 9% odcienia akcentu.
- **Wypełnienie wewnętrzne:** wiersze 14 × 16 px, wcięte separatory zaczynają się tam, gdzie tekst.

### Nawigacja
- **Pasek tygodnia:** przyklejony, przezroczysty w spoczynku, po przyklejeniu matowy z cienką linią. Telefon: strzałki po
  bokach wyśrodkowanej etykiety tygodnia (z szewronem) i jej wiersza meta. Tablet i wyżej: etykieta i meta z lewej, strzałki
  zgrupowane z prawej.
- **Arkusz tygodni:** dolny arkusz na telefonach (uchwyt, przeciągnięcie w dół, Esc lub tło zamykają), wyśrodkowane okno od
  768 px. Lista wyboru wszystkich tygodni: wybrany ma rysowane ✓, bieżący niebieską kropkę i podpis „Bieżący tydzień”.
- **Pływająca pastylka:** kapsuła „Bieżący tydzień”, która wyskakuje z dołu na sprężynie tylko wtedy, gdy oddalisz się od
  bieżącego tygodnia.

### Karta „Teraz” (znak rozpoznawczy)
Karta-przycisk na górze strony, widoczna tylko wtedy, gdy dziś są zajęcia trwające lub jeszcze przed nami. Zawiera wiersz
stanu (kropka na żywo + „Teraz · do GG:MM” albo zegar + „Następne · za …”), przedmiot nagłówkiem, potem salę, godziny i rodzaj,
a pod cienką linią następne zajęcia. Jej kapsuła wypełnia się wraz z postępem zajęć, na starcie animując od pustej.
Dotknięcie przechodzi do tych zajęć w tygodniu i je podświetla.

### Mapa kampusu
Mapa jest zawsze ciemna. Zieleń parków i trawy, granat wody i stonowane odcienie zabudowy (kampus niebieskawy, handel
bursztynowy, przemysł fioletowy, szpitale różowe) nadają jej charakter, a bryły 3D mają chłodną paletę, jaśniejszą wraz z
wysokością. Ikony miejsc to okrągłe plakietki w kolorach kategorii z białym piktogramem i ciemną obwódką:

| Kategoria | Kolor | Kategoria | Kolor |
|---|---|---|---|
| Tramwaje | `#ff453a` | Stołówki | `#ff6b81` |
| Autobusy | `#32ade6` | Bufety | `#e0a458` |
| Akademiki | `#bf5af2` | Restauracje | `#ff7a45` |
| Domki | `#2dd4bf` | Bary | `#7d6bff` |
| Sklepy | `#ff9f0a` | Paczkomaty | `#ffd60a` |
| Parkingi | `#5e86e8` | | |

## Zasady i przeciwwskazania

### Rób:
- **Rób** czarne tło `#000` i unoś powierzchnie tylko przez rampę `surface-*` oraz krawędź światła.
- **Używaj** akcentu wyłącznie dla „teraz”, „dziś”, fokusu i zaznaczenia (reguła jednego niebieskiego).
- **Animuj** transform i opacity: 150 ms dla odpowiedzi na dotyk, 300 ms dla zmian stanu, 420–520 ms dla przejść i arkuszy,
  expo-out (`cubic-bezier(0.22,1,0.36,1)`) dla wejść, `cubic-bezier(0.32,0.72,0,1)` dla arkusza, sprężyny dla wciśnięcia i
  pływającej pastylki.
- **Dawaj** każdemu ruchowi ścieżkę dla ograniczonego ruchu, która zachowuje zanikanie i skraca przesunięcia.
- **Trzymaj** całą stylizację w hashowanych blokach `<style>`, a wartości dynamiczne ustawiaj przez zmienne CSSOM. CSP blokuje
  atrybuty `style`.

### Nie rób:
- **Nie dodawaj** kolorowych poświat, tekstu z gradientem, pasków po bokach kart ani ikon-emoji i glifów.
- **Nie używaj** nadtytułów i etykiet kapitalikami ani kroju o stałej szerokości dla danych.
- **Nie rozmywaj** tła niczego, co nie unosi się nad treścią, i nie zapętlaj animacji elementów, które nie są „na żywo”.
- **Nie barw** tekstu ani powierzchni kolorami przedmiotów (reguła kapsuły).
- **Nie dodawaj** logo, herbu ani oficjalnie brzmiących sformułowań WAT: strona jest nieoficjalnym widokiem studentów.

## Motyw jasny i druk

Rampa ciemna powyżej jest referencyjna. `src/theme-light.css` powtarza te same tokeny dla jasnego motywu (szare tło grupowanych
list `#f2f2f7`, białe powierzchnie, cienkie linie `rgba(0,0,0,0.12)`, niebieski linków `#0060df`). `build.py` wstrzykuje go
razem ze stylami przełącznika i niewielkim wczesnym skryptem, dzięki czemu zapamiętany wybór działa przed pierwszym
malowaniem. Tryb Auto podąża za `prefers-color-scheme`. Dosłowne odcienie bieli i czerni są tokenami (`--hl`,
`--past-1/2`, `--warn`, `--scrim`), nigdy wartościami wpisanymi na stałe. Mapa pozostaje ciemna.

Druk („Drukuj / PDF”) to osobny układ w `src/group.html`: pokazywany tydzień na jednym arkuszu A4, czarno na białym, linia pod
każdym dniem, jedna linia na zajęcia (godzina, przedmiot z rodzajem, sala), kolor przedmiotu jako cienki pasek. `@page { margin: 0 }`
z wypełnieniem body powstrzymuje przeglądarkę przed dodaniem własnego nagłówka i stopki z adresem i datą.

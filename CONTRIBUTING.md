<div align="center">

<img src="src/icons/icon.svg" alt="PlanWAT" width="64" height="64">

# Współtworzenie PlanWAT

**Dziękujemy za pomoc.** Mile widziane są nowe i poprawione plany, poprawki błędów, dostępność i dokumentacja.

[![PR-y mile widziane](https://img.shields.io/badge/PR--y-mile%20widziane-brightgreen?style=flat)](#pull-requesty)
[![CI](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml)
[![Kodeks postępowania](https://img.shields.io/badge/kodeks%20post%C4%99powania-Contributor%20Covenant%202.1-blueviolet?style=flat)](CODE_OF_CONDUCT.md)
[![Licencja: MIT](https://img.shields.io/badge/licencja-MIT-green?style=flat)](LICENSE)
[![Podpisane commity](https://img.shields.io/badge/commity-podpisane-blue?style=flat&logo=git&logoColor=white)](#podpisane-commity)

</div>

---

## Spis treści

- [Jak możesz pomóc](#jak-możesz-pomóc)
- [Zgłaszanie podatności](#zgłaszanie-podatności)
- [Środowisko deweloperskie](#środowisko-deweloperskie)
- [Sprawdzenia przed pull requestem](#sprawdzenia-przed-pull-requestem)
- [Konwencje](#konwencje)
- [Podpisane commity](#podpisane-commity)
- [Pull requesty](#pull-requesty)
- [Kodeks postępowania](#kodeks-postępowania)

---

## Jak możesz pomóc

| Chcesz… | Zrób to |
|---|---|
| **Dodać grupę lub nowy semestr** | Dodaj `timetables/<semestr>/<GRUPA>.ics` zgodnie z [docs/ICS-FORMAT.md](docs/ICS-FORMAT.md) i otwórz PR albo [zgłoszenie planu](https://github.com/kilerdevs/PlanWAT/issues/new?template=timetable.yml) z linkiem do oficjalnego planu |
| **Poprawić błędne zajęcia** (sala, godzina) | Zmień zdarzenie w `.ics` grupy, zachowaj jego `UID` i otwórz PR albo zgłoszenie planu |
| **Naprawić błąd** | Otwórz [zgłoszenie błędu](https://github.com/kilerdevs/PlanWAT/issues/new?template=bug_report.yml) albo od razu PR przy małych poprawkach |
| **Zaproponować funkcję** | Przy czymkolwiek nietrywialnym najpierw otwórz [propozycję funkcji](https://github.com/kilerdevs/PlanWAT/issues/new?template=feature_request.yml) |
| **Poprawić dokumentację** | README, `docs/`, ten plik albo komentarz tam, gdzie warto uzasadnić niejasną decyzję |

Projekt ma [licencję MIT](LICENSE). Przesyłając pull request, zgadzasz się, że Twój wkład jest udostępniany na tej samej
licencji.

> [!NOTE]
> Plany nie zawierają danych kadry: bez nazwisk, tytułów, kontaktów ani linii z prowadzącym. Build odrzuci kalendarz, który je ma.

## Zgłaszanie podatności

> [!CAUTION]
> **Nie otwieraj publicznego zgłoszenia z podatnością.** Użyj prywatnego zgłaszania. Zasady, zakres i terminy odpowiedzi
> opisuje [SECURITY.md](SECURITY.md).

## Środowisko deweloperskie

Potrzebujesz Pythona 3.12+ i Node.js 22+.

```bash
git clone https://github.com/kilerdevs/PlanWAT.git && cd PlanWAT
git switch dev
npm ci
npx playwright install chromium               # dodaj firefox webkit, by uruchomić całą macierz przeglądarek
python3 build.py && node tests/e2e/serve.js   # podgląd na http://127.0.0.1:4173
```

## Sprawdzenia przed pull requestem

```bash
npm test        # testy czytnika i budowy, potem testy przeglądarkowe na świeżej budowie
```

CI uruchamia te same sprawdzenia oraz Firefoksa i WebKit, skan i test dymny obrazu Docker oraz CodeQL. Przy zmianach
interfejsu obejrzyj wynik także na prawdziwym telefonie i z włączonym ograniczeniem ruchu.

## Konwencje

- **Najpierw test.** Zmiany czytnika dostają przypadek w `tests/ics.test.js`, logiki planu w `tests/insights.test.js`,
  budowy w `tests/test_build.py`, a zachowanie w przeglądarce w `tests/e2e/site.spec.js`. Obejrzyj, jak pada, potem napraw.
- **Bez zależności w runtime i bez skryptów firm trzecich.** Strona to zwykłe HTML, CSS i JavaScript. Pakiety npm służą tylko
  testom.
- **CSP pozostaje rygorystyczne.** Cały skrypt i styl mieszkają w blokach `<script>` / `<style>` szablonów, które build
  haszuje. Bez atrybutów `style="…"` ani obsługi `on…=`: wartości dynamiczne ustawiaj przez `element.style.setProperty`.
  Dane z kalendarza renderuj przez `textContent`, nigdy `innerHTML`.
- **Wygląd:** stosuj [DESIGN.md](DESIGN.md) (tokeny, jeden akcent, zasady ruchu, cele dotyku 44 px) i dbaj o płynność na
  zwykłych telefonach: animuj `transform` i `opacity`, szanuj `prefers-reduced-motion`.
- **Teksty:** interfejs jest po polsku. Kod i komentarze są po angielsku, dokumentacja w repozytorium po polsku.
- **Kalendarze** zachowują zakończenia linii CRLF i stabilne `UID`.
- **Bez danych osobowych kadry**, w żadnej formie, także w testach i logach.
- Styl: wcięcie 2 spacje w HTML/CSS/JS, 4 w Pythonie. Zob. [.editorconfig](.editorconfig).

## Podpisane commity

`master` przyjmuje wyłącznie podpisane commity. Najprościej użyć klucza SSH:

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config commit.gpgsign true
git config tag.gpgsign true
```

Potem dodaj ten sam klucz publiczny na GitHubie w **Settings → SSH and GPG keys → New SSH key** z typem klucza
**Signing Key** i commituj z adresem e-mail zweryfikowanym na koncie. Klucze GPG również działają.

## Pull requesty

- Rozgałęziaj od `dev` i otwieraj PR do **`dev`**. Wydania to PR-y z `dev` do `master`, który wdraża.
- Jeden temat na PR i wypełniony szablon.
- Dodaj wiersz w **Unreleased** w [CHANGELOG.md](CHANGELOG.md) dla wszystkiego, co użytkownik zauważy.
- Komunikaty commitów: krótkie podsumowanie w trybie rozkazującym, opcjonalnie z prefiksem obszaru (`Reader: …`, `Build: …`,
  `CI: …`, `Timetable: …`).

## Kodeks postępowania

Projekt stosuje [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Problemy z zachowaniem zgłaszaj prywatnie przez
[security advisories](https://github.com/kilerdevs/PlanWAT/security/advisories/new) z tytułem zaczynającym się od
„Conduct report”.

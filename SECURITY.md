<div align="center">

<img src="src/icons/icon.svg" alt="PlanWAT" width="64" height="64">

# Polityka bezpieczeństwa

[![Zgłoś podatność](https://img.shields.io/badge/zg%C5%82o%C5%9B-prywatnie%20przez%20GitHub-critical?style=flat&logo=github)](https://github.com/kilerdevs/PlanWAT/security/advisories/new)
[![Potwierdzenie](https://img.shields.io/badge/potwierdzenie-48%20h-blue?style=flat)](#czego-się-spodziewać)
[![Cel naprawy](https://img.shields.io/badge/cel%20naprawy-30%20dni-blue?style=flat)](#czego-się-spodziewać)
[![SAST](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml)
[![CodeQL](https://img.shields.io/badge/CodeQL-JS%20%C2%B7%20Python%20%C2%B7%20Actions-success?style=flat&logo=github&logoColor=white)](https://github.com/kilerdevs/PlanWAT/security/code-scanning)

</div>

PlanWAT to publiczna strona statyczna bez kont i bez przechowywanych danych osobowych. Cele bezpieczeństwa są trzy: w
przeglądarce odwiedzającego ma działać wyłącznie jej własny kod, plik kalendarza nie może wstrzyknąć znaczników ani
skryptu, a samodzielnie hostowany obraz ma udostępniać tylko zbudowane pliki.

> [!NOTE]
> Najlepszy sposób ochrony danych to ich nie zbierać. PlanWAT nie ma formularza logowania, nie prosi o adres e-mail ani o
> żadne inne dane osobowe i nie ma gdzie ich zapisać. Gdyby ktoś w imieniu PlanWAT o nie prosił, to szemrane zachowanie, o którym
> warto nas zawiadomić.

## Spis treści

- [Wspierane wersje](#wspierane-wersje)
- [Zgłaszanie podatności](#zgłaszanie-podatności)
- [Czego się spodziewać](#czego-się-spodziewać)
- [Zakres](#zakres)
- [Bezpieczna przystań](#bezpieczna-przystań)

---

## Wspierane wersje

| Wersja | Wspierana |
|---|---|
| Aktualny `master` (to, co jest wdrożone) | ✅ |
| Cokolwiek starszego | ❌ |

Poprawki powstają na `dev` i trafiają na `master` z najbliższym wydaniem.

## Zgłaszanie podatności

> [!IMPORTANT]
> **Nie otwieraj publicznego zgłoszenia GitHub w sprawie problemów bezpieczeństwa.**

Preferowany kanał: prywatne zgłaszanie podatności GitHub (Private Vulnerability Reporting).

> <https://github.com/kilerdevs/PlanWAT/security/advisories/new>

Jeśli nie możesz z niego skorzystać, otwórz zwykłe zgłoszenie zatytułowane wyłącznie `[security] please contact you privately`,
bez żadnych szczegółów technicznych, i poczekaj, aż opiekun się z Tobą skontaktuje.

### Co dołączyć

- Dotknięty plik, stronę lub adres URL oraz ścieżkę w kodzie
- Kroki odtworzenia lub dowód koncepcji (np. spreparowany plik `.ics`)
- Skutki: co zyskuje atakujący i przy jakich warunkach
- Przeglądarkę i system albo środowisko (GitHub Pages, obraz Docker)

## Czego się spodziewać

| Kiedy | Co się dzieje |
|---|---|
| **48 godzin** | Potwierdzenie przyjęcia zgłoszenia |
| **7 dni** | Wstępna ocena: potwierdzone / to nie podatność / potrzebne dodatkowe informacje |
| **30 dni** | Poprawka wdrożona lub udokumentowane obejście, dla potwierdzonych problemów |

Zostaniesz wymieniony w dzienniku zmian i w poradniku bezpieczeństwa, chyba że wolisz pozostać anonimowy. Prosimy o rozsądne
okno przed publicznym ujawnieniem (zwyczajowo 90 dni).

## Zakres

### W zakresie

| Obszar | Przykłady |
|---|---|
| `src/ics.js` | Kalendarz, który sprawia, że czytnik wykonuje kod, zawiesza się albo renderuje kontrolowane przez atakującego znaczniki |
| `src/group.html`, `src/index.html`, `src/404.html`, `src/mapa.html`, `src/prywatnosc.html` | XSS, DOM clobbering, obejścia CSP, niebezpieczne użycie danych z kalendarza |
| `src/sw.js` | Service Worker buforujący lub serwujący to, czego nie powinien (inny origin, żądanie inne niż GET, strony drugiego wdrożenia) |
| `build.py` | Metadane uciekające z escapowania HTML, path traversal przez nazwy grup lub semestrów, strona wysłana bez CSP |
| `deploy/nginx.conf`, `Dockerfile`, `docker-compose.yml` | Serwowany plik, który nie powinien, brakujące nagłówki, uprawnienia lub zapis w kontenerze |
| `.github/workflows/` | Wstrzyknięcie do workflowu, nadmierne uprawnienia tokenu, nieprzypięty kod firm trzecich |
| `tools/refresh/`, `tools/egress/` | Ucieczka z izolacji runnera, wyciek tokenu, żądania poza listą dozwolonych hostów |

### Poza zakresem

- **Błędne dane planu** (sala lub godzina): otwórz zamiast tego
  [zgłoszenie planu](https://github.com/kilerdevs/PlanWAT/issues/new?template=timetable.yml).
- Nagłówki, których GitHub Pages nie potrafi wysłać (`X-Frame-Options`, `frame-ancestors`, …): udokumentowane wraz ze
  sposobem ich odtworzenia w [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#nagłówki-bezpieczeństwa-na-pages).
- Skrypty wstrzykiwane przez pośrednika, np. wykrywanie botów w proxy: CSP strony je blokuje.
- Ładowanie kroju Inter z Google Fonts: udokumentowane, świadome żądanie do strony trzeciej.
- Wyłącznie na mapie kampusu (`/mapa/`): ładowanie MapLibre GL JS z unpkg (z SRI) i kafelków z OpenFreeMap, oba udokumentowane
  i świadome.
- Ataki typu odmowa usługi na infrastrukturę GitHub Pages oraz wyniki automatycznych skanerów bez wykazanego skutku.

## Bezpieczna przystań

Badania prowadzone w dobrej wierze zgodnie z tą polityką są mile widziane: nie podejmiemy z ich powodu kroków prawnych.
Pozostań w opisanym zakresie, nie pogarszaj działania usługi innym użytkownikom i nie sięgaj po dane, które nie są Twoje.
Zawsze lepsze są testy na własnej, lokalnej budowie (`python3 build.py` i `node tests/e2e/serve.js` albo obraz Docker).

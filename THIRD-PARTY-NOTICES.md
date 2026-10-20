<div align="center">

<img src="src/icons/icon.svg" alt="PlanWAT" width="64" height="64">

# Oprogramowanie i dane firm trzecich

[![Zależności w runtime](https://img.shields.io/badge/zale%C5%BCno%C5%9Bci%20w%20runtime-zero-brightgreen?style=flat)](#dostarczane-z-serwisem)
[![Ikony: Lucide](https://img.shields.io/badge/ikony-Lucide%20(ISC)-f56565?style=flat)](#ikony-lucide)
[![Mapa: OpenStreetMap](https://img.shields.io/badge/dane%20mapy-OpenStreetMap%20(ODbL)-7ebc6f?style=flat&logo=openstreetmap&logoColor=white)](#dane)
[![MapLibre](https://img.shields.io/badge/MapLibre%20GL%20JS-4.7.1-396cb2?style=flat)](#mapa-kampusu)

</div>

PlanWAT niczego nie ładuje z cudzych serwerów: wszystko, co opisano niżej, leży w repozytorium i jest serwowane z samej
strony. Narzędzia deweloperskie podano dla kompletności: nigdy nie trafiają do zbudowanej strony.

## Dostarczane z serwisem

### Ikony Lucide

Liniowe ikony w `src/group.html` (szewrony, pinezka, użytkownik, zegar, zamknięcie, obrót, kalendarz, ostrzeżenie, pobieranie,
pytajnik i inne) to ścieżki z [Lucide](https://lucide.dev), używane na licencji ISC. Tekst licencji pozostawiamy w oryginale:

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c)
for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted,
provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

Piktogramy ikon miejsc na mapie (sklep, dom, autobus, tramwaj, paczka, sztućce i inne) są rysowane na podstawie tych samych
ścieżek Lucide.

### Krój Inter

[Inter](https://github.com/rsms/inter) (zapasowy tam, gdzie nie ma SF Pro) leży w `src/fonts/` w dwóch podzbiorach, łacińskim
i łacińskim rozszerzonym (pliki woff2 w postaci, w jakiej udostępnia je Google Fonts), a budowa publikuje go w `assets/`.
Copyright (c) 2016 The Inter Project Authors, na licencji SIL Open Font License 1.1. Pełny tekst licencji:
[`src/fonts/OFL.txt`](src/fonts/OFL.txt).

### Mapa kampusu

Wszystko, czym rysuje mapa `/mapa/`, leży w `src/map/` (odtwarzane skryptem `tools/map/vendor_map.py`) i jest publikowane pod
`mapa/`:

| Składnik | Pochodzenie | Licencja |
|---|---|---|
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) 4.7.1 (`lib/`) | paczka npm `maplibre-gl`, bajty sprawdzane sumą SRI ze strony | BSD-3-Clause, [`src/map/lib/LICENSE.txt`](src/map/lib/LICENSE.txt) |
| Wektorowe kafelki (`tiles/`) | [OpenFreeMap](https://openfreemap.org), schemat [OpenMapTiles](https://openmaptiles.org) | Dane © [współtwórcy OpenStreetMap](https://www.openstreetmap.org/copyright), ODbL 1.0; © OpenMapTiles |
| Styl `dark` (`style.json`) i ikony (`sprites/`) | [OpenFreeMap styles](https://github.com/hyperknot/openfreemap-styles) | MIT; styl wywodzi się ze stylów OpenMapTiles (kod BSD-3-Clause, projekt CC BY 4.0); ikony Maki CC0 1.0; [`src/map/LICENSE-openfreemap.md`](src/map/LICENSE-openfreemap.md) |
| Glify etykiet (`glyphs/`, Noto Sans) | OpenFreeMap | SIL Open Font License 1.1 |

Mapa pokazuje te podziękowania także w swoim przycisku atrybucji.

## Dane

### Współrzędne budynków kampusu

Położenie i opisy budynków w `src/campus.js` to wtórna baza centroidów budynków
[OpenStreetMap](https://www.openstreetmap.org/copyright), opracowana i opublikowana przez Plan WAT (planwat.pl,
`campus-building-coordinates.json`). Dane mapy © współtwórcy OpenStreetMap. Baza jest dostępna na
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/), a reszta tego repozytorium pozostaje na własnej
licencji MIT. Nie zawiera planów ani danych użytkowników.

### Miejsca wokół kampusu

Przystanki, akademiki, sklepy, parkingi, paczkomaty i miejsca z jedzeniem w `src/places.js` zostały wyodrębnione z
[OpenStreetMap](https://www.openstreetmap.org/copyright) skryptem `tools/places/make_places.py` (Overpass API, uruchamianym
ręcznie, nigdy przez serwis). Dane mapy © współtwórcy OpenStreetMap, dostępne na
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/). Wpis „Domki Radiowa” został dodany ręcznie.

## Tylko do rozwoju

| Narzędzie | Do czego | Licencja |
|---|---|---|
| [@playwright/test](https://playwright.dev) | Testy przeglądarkowe | Apache-2.0 |
| [@axe-core/playwright](https://github.com/dequelabs/axe-core-npm), [axe-core](https://github.com/dequelabs/axe-core) | Kontrole dostępności | MPL-2.0 |
| `python:3.13-alpine`, `nginxinc/nginx-unprivileged` | Obrazy Docker do budowy i uruchomienia | Zob. każdy obraz |

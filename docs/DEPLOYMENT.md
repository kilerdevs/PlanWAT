<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Wdrożenie

**Strona statyczna: GitHub Pages albo wzmocniony obraz Docker.**

[![Pages](https://github.com/kilerdevs/PlanWAT/actions/workflows/pages.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/pages.yml)
![GitHub Pages](https://img.shields.io/badge/hosting-GitHub%20Pages-222?style=flat&logo=github&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-nginx%20read--only-2496ED?style=flat&logo=docker&logoColor=white)
![Nagłówki](https://img.shields.io/badge/nag%C5%82%C3%B3wki-tylko%20w%20Dockerze-orange?style=flat)

</div>

PlanWAT to strona statyczna. Działa na GitHub Pages (docelowo) albo na samodzielnie hostowanym obrazie Docker za reverse
proxy. W przykładach własna domena to `plan.example.org`.

<img src="diagrams/budowa-strony.svg" alt="Pliki .ics przechodzą przez build.py do site/, a stamtąd na GitHub Pages albo do obrazu Docker." width="760">

## GitHub Pages

[`.github/workflows/pages.yml`](../.github/workflows/pages.yml) buduje `site/` i wdraża go:

- po każdym pushu na `master` (chroniony: podpisane commity i zielone CI),
- codziennie o 03:17 UTC, żeby nowy semestr startował pierwszego dnia bez commita,
- ręcznie z zakładki Actions (**Run workflow**).

Serwis jest wtedy dostępny pod <https://kilerdevs.github.io/PlanWAT/>. Wszystkie linki są względne, więc działa to zarówno
tam, jak i na własnej domenie. Ścieżki bazowej potrzebuje tylko strona 404, którą workflow pobiera z
`actions/configure-pages`.

### Podgląd dev

Każde wdrożenie buduje też szczyt `dev` do `/dev/` (np. <https://kilerdevs.github.io/PlanWAT/dev/>), z linkiem „Wersja
testowa (dev)” w stopce produkcyjnej strony głównej i „Wersja stabilna” wracającym. Push na `dev` odświeża podgląd, a
produkcja zawsze powstaje z `master`, więc push na `dev` nigdy nie wypromuje niedokończonej treści do katalogu głównego.
Codzienna przebudowa odświeża także wybór bieżącego semestru w podglądzie. Podgląd powstaje z `--noindex` (znacznik
`noindex, nofollow` na każdej stronie i zamknięty `robots.txt`) i ma własny Service Worker pod `/dev/sw.js`, w który
produkcyjny nie ingeruje.

`robots.txt` i `/.well-known/security.txt` są czytane tylko w katalogu głównym hosta, więc pod `kilerdevs.github.io/PlanWAT/`
zadziałają dopiero po ustawieniu własnej domeny. Artefakt Pages zawiera pliki z kropką dla `.well-known/` i usuwa wewnętrzne
znaczniki budowy `.planwat-site`.

### Wyszukiwarki

Każda strona ma własny tytuł i opis pod frazy, których ludzie szukają („plan zajęć WAT”, „plan zajęć WCY26KY3S1”), kartę
Open Graph do podglądu linków i dane strukturalne JSON-LD (`WebSite` na stronie głównej, okruszki `BreadcrumbList` na
stronach grup). Produkcja budowana jest z `--site-url` (adres `base_url` z `actions/configure-pages`), więc strony dostają też
adres kanoniczny, a serwis `sitemap.xml` ze wszystkimi grupami i datą ostatniej zmiany planu. Po przejściu na własną domenę
adresy zmienią się same. Podgląd dev nie dostaje mapy witryny.

Pod `kilerdevs.github.io/PlanWAT/` są dwa ograniczenia, których kod nie obejdzie: Google ustala **nazwę witryny i favicon dla
całego hosta** (`kilerdevs.github.io`, gdzie nie ma strony głównej, stąd „GitHub Pages documentation” i ikona globusa), a
`robots.txt` czyta tylko z katalogu głównego hosta. Naprawia to własna domena (zob. niżej) albo repozytorium
`kilerdevs.github.io` ze stroną główną, która przedstawia się jako PlanWAT.

Jednorazowo w [Google Search Console](https://search.google.com/search-console) (właściwość z prefiksem URL
`https://kilerdevs.github.io/PlanWAT/`, weryfikowana znacznikiem na stronie głównej):

1. **Mapy witryn** → dodaj `sitemap.xml`.
2. **Sprawdzanie adresu URL** → strona główna → **Poproś o zindeksowanie**.
3. W [Bing Webmaster Tools](https://www.bing.com/webmasters) zaimportuj witrynę z Search Console (obejmuje też DuckDuckGo
   i Ecosia).

### Mapa kampusu

Mapa `/mapa/` niczego nie pobiera z innych serwerów: silnik, styl, kafelki, glify i ikony leżą w `src/map/`.
[`.github/workflows/map.yml`](../.github/workflows/map.yml) odświeża je raz w miesiącu (2. dnia, też ręcznie z zakładki
Actions): uruchamia `tools/map/vendor_map.py`, a gdy coś się zmieniło, buduje stronę, puszcza testy budowy i testy
przeglądarkowe mapy i dopiero wtedy publikuje pliki na gałęzi `map`. Pages nakłada je na `src/map/` (tak jak gałąź `data`
na plany), ale tylko w drzewie, które oczekuje dokładnie tych kafelków i tej wersji silnika; inaczej zostaje mapa zapisana w
repozytorium.

Gałąź `map` ma zawsze jeden commit, zastępowany przy każdej aktualizacji: miesiąc kafelków to ok. 26 MB po kompresji, więc
commitowane na `dev` co miesiąc powiększałyby historię repozytorium o tyle samo. Gdy zmienią się granice mapy
(`src/campus.js`) albo wersja MapLibre, uruchom `node tools/map/coverage.js` i `python3 tools/map/vendor_map.py` i zacommituj
wynik razem z kodem.

> [!NOTE]
> GitHub wyłącza zaplanowane workflowy w publicznych repozytoriach po 60 dniach bez aktywności. Jeśli to się stanie, włącz
> ponownie **Pages** w zakładce Actions (albo wypchnij dowolny commit).

### Przeniesienie własnej domeny na Pages

1. W repozytorium **Settings → Pages → Custom domain** wpisz `plan.example.org` i zapisz. GitHub przechowuje to ustawienie
   sam, a przy wdrożeniu przez Actions plik `CNAME` nie jest potrzebny.
2. U dostawcy DNS skieruj `plan` na Pages rekordem `CNAME plan → kilerdevs.github.io`. Gdy GitHub pokaże wydany certyfikat,
   włącz **Enforce HTTPS** w ustawieniach Pages.
3. Następna budowa Pages sama przejmie nową ścieżkę bazową (pustą). Sprawdź `https://plan.example.org/` i stronę grupy. Jeśli
   wcześniej domenę obsługiwał kontener Docker, zatrzymaj go (`docker compose down` w katalogu projektu).

### Nagłówki bezpieczeństwa na Pages

GitHub Pages nie potrafi wysyłać własnych nagłówków. Co nadal działa i jak odtworzyć resztę:

| Zabezpieczenie | Na Pages |
|---|---|
| Content-Security-Policy (skrypty, style, fetch, base-uri, form-action) | Tak: każda strona ma ją w znaczniku `<meta>`. |
| HTTPS, HSTS | Tak na `*.github.io`, a na własnej domenie po włączeniu **Enforce HTTPS**. |
| `frame-ancestors` / `X-Frame-Options` (zakaz osadzania) | Nie: przeglądarki ignorują `frame-ancestors` w znaczniku meta. |
| `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP | Nie (każda strona ustawia `referrer` na `no-referrer` przez meta). |

Żeby je mieć, serwuj stronę z obrazu Docker poniżej (jego nginx wysyła wszystkie) albo postaw Pages za proxy lub CDN, które
potrafią dodawać nagłówki odpowiedzi, ustawione na:

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()
Cross-Origin-Opener-Policy: same-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

## Docker (własny hosting)

```bash
docker compose up -d --build
```

[`Dockerfile`](../Dockerfile) buduje w dwóch etapach:

1. `python:3.13-alpine` uruchamia `build.py`, który zapisuje `site/` i wpisuje hashe CSP każdej strony (razem ze
   źródłami wspólnych plików `assets/`) do kopii [`deploy/nginx.conf`](../deploy/nginx.conf) (CSP w nagłówku, razem
   z `frame-ancestors`).
2. `nginx-unprivileged` (przypięty digestem, po `apk upgrade`) serwuje wyłącznie te pliki.

[`docker-compose.yml`](../docker-compose.yml) uruchamia go tylko do odczytu, jako użytkownik inny niż root, z odebranymi
wszystkimi uprawnieniami (capabilities), `no-new-privileges`, limitami pamięci, CPU i procesów oraz portem związanym wyłącznie
z `127.0.0.1:8088`. Udostępnij go przez reverse proxy kończące TLS (i ustaw nagłówek adresu klienta w `deploy/nginx.conf`).
nginx dopuszcza tylko `GET`/`HEAD`, ogranicza liczbę żądań na adres klienta i wysyła nagłówki bezpieczeństwa z listy wyżej.

Semestry są wybierane w momencie budowy obrazu, więc **przebuduj obraz, gdy zaczyna się nowy semestr** (albo przejdź na Pages,
które przebudowuje się codziennie).

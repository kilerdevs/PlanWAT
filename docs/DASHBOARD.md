<div align="center">

<img src="../src/icons/icon.svg" alt="PlanWAT" width="56" height="56">

# Panel floty

**Podgląd przebiegów odświeżania na żywo, tylko na komputerze operatora.**

![Dostęp](https://img.shields.io/badge/dost%C4%99p-127.0.0.1%20%3A8765-informational?style=flat)
![Telemetria](https://img.shields.io/badge/telemetria-AES--GCM-success?style=flat)

</div>

Panel ([`tools/dash/dash.py`](../tools/dash/dash.py)) pokazuje, co robi cała flota w trakcie przebiegu i jak szły
poprzednie przebiegi. Rozumie [stos pracy](REFRESH.md#stos-pracy): sloty, kawałki, ściany, polowania na wyjścia i drogi,
którymi runnery docierają do wydziałów. Działa wyłącznie lokalnie: serwer słucha tylko na `127.0.0.1`, niczego nie
wystawia w sieci i nic nie zapisuje w GitHubie.

## Uruchomienie

```sh
python3 tools/dash/dash.py            # otwiera http://127.0.0.1:8765/
python3 tools/dash/dash.py --no-browser --port 8765
```

Potrzebne są `git`, zalogowany `gh` (lista przebiegów i zadań) i pakiet `cryptography` (odczyt telemetrii). Panel
działa też bez klucza, ale wtedy widać tylko stos pracy i przebiegi.

### Klucz (jednorazowo)

Repozytorium jest publiczne, więc referencje stosu może czytać każdy. Telemetria runnerów jest dlatego szyfrowana
(AES-GCM) kluczem, który znają tylko sekret w GitHubie i ten komputer:

```sh
mkdir -p ~/.config/planwat
python3 -c 'import secrets; print(secrets.token_hex(32))' > ~/.config/planwat/dash.key
chmod 600 ~/.config/planwat/dash.key
gh secret set PLANWAT_DASH_KEY < ~/.config/planwat/dash.key
```

Klucz nie trafia do repozytorium ani do logów. Zamiast pliku można ustawić zmienną `PLANWAT_DASH_KEY`. Bez sekretu
runnery po prostu nie dołączają telemetrii, a crawl działa jak wcześniej. Wolontariusze tego sekretu nie dostają.

## Skąd są dane

| Źródło | Co daje | Jak często |
|---|---|---|
| stos pracy (`refs/planwat/pass/…`, [`board.py`](../tools/refresh/board.py)) | sloty, kawałki i kto je zrobił, ściany (`cant`), polowania, drogi (`via`, `via_tor`), pasy runnerów | co 10 s |
| telemetria na biciu serca (`tel`, [`telemetry.py`](../tools/refresh/telemetry.py)) | obciążenie (CPU, load, pamięć, RSS crawla, sieć), odpowiedzi według hosta i drogi, Tor, ostatnie polowania, ostatnie 60 linii logu | runner wysyła co 15 s |
| `gh api` (workflow `refresh.yml`) | przebiegi i zadania: kolejka, czas, wynik, runner | co 30 s |
| archiwum (`refs/planwat/archive/…`, `board.py archive`) | ostatnie dokumenty przebiegu, którego panel nie oglądał na żywo | po każdym przebiegu, 30 dni |

Panel pobiera referencje do własnego repozytorium podręcznego (`~/.cache/planwat-dash/git`), nigdy do checkoutu. To,
co zobaczył, trzyma w SQLite (`~/.local/share/planwat-dash/dash.db`) przez 60 dni. Logi zadań w GitHub Actions są
publiczne jak dotąd. Szyfrowanie dotyczy tylko telemetrii, której wcześniej nigdzie nie było.

## Co pokazuje

**Na żywo**

- kafelki: przebieg (link), czas, grupy sprawdzone i zmienione kalendarze, otwarte wydziały, pracujące runnery, strony
  na minutę całej floty, liczba ścian;
- **Wydziały**: pasek kawałków w kolorze runnera, który je sprawdził (kreskowany: sprawdza teraz), lider, liczby z
  listy (świeże, niegotowe) i drogi każdego runnera: własny adres, własny Tor, wyjścia z puli, poluje, ściana;
- **Runnery**: stan (crawl, listuje, poluje, czeka, koniec, zniknął), wiek bicia serca, pasy z bieżącym kawałkiem,
  strony na minutę, odpowiedzi według kodów i dróg, CPU, load, pamięć, sieć, Tor i ostatnie polowania;
- **Oś czasu**: wiersz na każdy pas runnera, z wydziałami, polowaniami i przerwami. Od razu widać bezczynność;
- **Zdarzenia**: zmiany na stosie (otwarcie, koniec, ściana, polowanie, przejście przez wyjścia, dołączenie) i linie logu
  runnerów, z filtrami.

**Historia** (3–60 dni): czas przebiegów, wykorzystanie runnerów (udział próbek w każdym stanie), udział w pracy, drogi
do wydziałów w kolejnych przebiegach, kolejka GitHuba i wyniki zadań według runnera, lista przebiegów.

## Bezpieczeństwo

- Serwer wiąże się tylko z `127.0.0.1` i odpowiada wyłącznie na nagłówek `Host` `127.0.0.1:<port>` albo
  `localhost:<port>` (inaczej 421), więc obca strona nie przepnie swojej domeny na ten port (DNS rebinding).
- Tylko `GET`, bez CORS, ze ścisłym CSP (`script-src 'self'`). Tekst od runnerów trafia na stronę wyłącznie jako tekst.
- Plik klucza z uprawnieniami szerszymi niż `600` daje ostrzeżenie przy starcie.

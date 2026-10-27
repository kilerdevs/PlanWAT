# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 27 paź 2026 · 09:03 · **oracle** · ~~plebania~~ · 55 min · [przebieg #73](https://github.com/kilerdevs/PlanWAT/actions/runs/40470944765)
> Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 27 paź · 09:03 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG) · ~~plebania~~ | 349 | 55 min | [#73](https://github.com/kilerdevs/PlanWAT/actions/runs/40470944765) |
| 27 paź · 02:32 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG) · ~~plebania~~ | 393 | 48 min | [#72](https://github.com/kilerdevs/PlanWAT/actions/runs/40433154047) |
| 27 paź · 00:00 | Bez zmian | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (WIM, IOE, WIG) | 126 | 11 min | [#71](https://github.com/kilerdevs/PlanWAT/actions/runs/40416669173) |
| 26 paź · 23:48 | Zmiany w 33 planach | **oracle** (WIG) | 33 | 4 min | [#70](https://github.com/kilerdevs/PlanWAT/actions/runs/40415244881) |
| 26 paź · 22:06 | Zmiany w 2 planach | **plebania** (WLO, WEL, IOE, WCY, WML, WTC (od oracle)) · **oracle** (WIM, WTC) | 255 | 26 min | [#69](https://github.com/kilerdevs/PlanWAT/actions/runs/40401476129) |
| 26 paź · 20:01 | Zablokowany | **plebania** (WLO, WEL, WCY, WML, WIM (od oracle), WTC (od oracle)) · **oracle** (WIM, IOE, WTC, WML (od plebania)) | 485 | 60 min | [#68](https://github.com/kilerdevs/PlanWAT/actions/runs/40382908076) |
| 26 paź · 16:19 | Część stron odrzucona | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 110 | 10 min | [#67](https://github.com/kilerdevs/PlanWAT/actions/runs/40348126142) |
| 26 paź · 15:00 | Zmiany w 124 planach | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 735 | 41 min | [#66](https://github.com/kilerdevs/PlanWAT/actions/runs/40335568289) |
| 26 paź · 08:56 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC) · ~~plebania~~ | 261 | 55 min | [#65](https://github.com/kilerdevs/PlanWAT/actions/runs/40288910011) |
| 26 paź · 01:30 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC) · ~~plebania~~ | 42 | 32 min | [#64](https://github.com/kilerdevs/PlanWAT/actions/runs/40249645750) |

## Szczegóły

<details>
<summary><b>27 paź · 09:03</b> · Zablokowany · oracle</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#73](https://github.com/kilerdevs/PlanWAT/actions/runs/40470944765), od planu do raportu 55 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG | 5 | 54 min, zablokowany na WLO, WCY, WML, WTC |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 158 | 0 | odrzucone strony: 3 |
| WIM | oracle | 88 | 3 |  |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 55 | 2 | blokada Incapsula, odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |

</details>

<details>
<summary><b>27 paź · 02:32</b> · Zablokowany · oracle</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#72](https://github.com/kilerdevs/PlanWAT/actions/runs/40433154047), od planu do raportu 48 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG | 22 | 47 min, zablokowany na WLO, WML, WTC |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 115 | 0 | odrzucone strony: 3 |
| WIM | oracle | 88 | 1 |  |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 142 | 21 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |

</details>

<details>
<summary><b>27 paź · 00:00</b> · Bez zmian · plebania · oracle</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg uruchomiony ręcznie [#71](https://github.com/kilerdevs/PlanWAT/actions/runs/40416669173), od planu do raportu 11 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC | 0 | 10 min |
| **oracle** | WIM, IOE, WIG | 0 | 1 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 19 | 0 |  |
| WEL | plebania | 46 | 0 | odrzucone strony: 3 |
| WCY | plebania | 55 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 4 | 0 | odrzucone strony: 3 |
| WTC | plebania | 1 | 0 | odrzucone strony: 1 |
| WIM | oracle | 1 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WIG | oracle | 0 | 0 |  |

</details>

<details>
<summary><b>26 paź · 23:48</b> · Zmiany w 33 planach · oracle</summary>

Pobrano nowe wersje 33 planów. Przebieg uruchomiony ręcznie [#70](https://github.com/kilerdevs/PlanWAT/actions/runs/40415244881), od planu do raportu 4 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WIG | 33 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIG | oracle | 33 | 33 |  |

</details>

<details>
<summary><b>26 paź · 22:06</b> · Zmiany w 2 planach · plebania · oracle</summary>

Pobrano nowe wersje 2 planów. Przebieg automatyczny [#69](https://github.com/kilerdevs/PlanWAT/actions/runs/40401476129), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, IOE, WCY, WML | 1 | 25 min |
| **oracle** | WIM, WTC | 1 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | <1 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| IOE | plebania | 0 | 0 |  |
| WCY | plebania | 39 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 162 | 1 | odrzucone strony: 3 |
| WIM | oracle | 50 | 1 |  |
| WTC | plebania | 1 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>26 paź · 20:01</b> · Zablokowany · plebania · oracle</summary>

Strona wydziału WML, WIM zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#68](https://github.com/kilerdevs/PlanWAT/actions/runs/40382908076), od planu do raportu 60 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 28 min, zablokowany na WML |
| **oracle** | WIM, IOE, WTC | 2 | 6 min, zablokowany na WIM, WTC |
| **plebania** (przejęcie) | WIM (od oracle), WTC (od oracle) | 0 | 4 min, zablokowany na WIM |
| **oracle** (przejęcie) | WML (od plebania) | 0 | 31 min, zablokowany na WML |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 |  |
| WEL | plebania | 158 | 0 | odrzucone strony: 3 |
| WCY | plebania | 158 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | oracle | 0 | 0 | przejęty po blokadzie na plebania, blokada Incapsula |
| WIM | plebania | 0 | 0 | przejęty po blokadzie na oracle, blokada |
| IOE | oracle | 15 | 0 |  |
| WTC | plebania | 23 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>26 paź · 16:19</b> · Część stron odrzucona · plebania · oracle</summary>

Część stron (WEL) nie przeszła kontroli, więc zostają dla nich poprzednie plany. Przebieg automatyczny [#67](https://github.com/kilerdevs/PlanWAT/actions/runs/40348126142), od planu do raportu 10 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 9 min, niedokończony |
| **oracle** | WIM, IOE, WTC | 0 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | <1 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 28 | 0 |  |
| WEL | plebania | 6 | 0 | odrzucone strony: 3 z 6 |
| WCY | plebania | 54 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 11 | 0 | odrzucone strony: 3 |
| WIM | oracle | 10 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | plebania | 1 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>26 paź · 15:00</b> · Zmiany w 124 planach · plebania · oracle</summary>

Pobrano nowe wersje 124 planów. Przebieg uruchomiony ręcznie [#66](https://github.com/kilerdevs/PlanWAT/actions/runs/40335568289), od planu do raportu 41 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 114 | 36 min |
| **oracle** | WIM, IOE, WTC | 10 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | 4 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 28 |  |
| WEL | plebania | 158 | 46 | odrzucone strony: 3 |
| WCY | plebania | 158 | 31 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 162 | 9 | odrzucone strony: 3 |
| WIM | oracle | 88 | 10 |  |
| IOE | oracle | 15 | 0 |  |
| WTC | plebania | 23 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>26 paź · 08:56</b> · Zablokowany · oracle</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#65](https://github.com/kilerdevs/PlanWAT/actions/runs/40288910011), od planu do raportu 55 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, WIM, IOE, WCY, WML, WTC | 2 | 54 min, zablokowany na WLO, WCY, WML, WTC |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 158 | 0 | odrzucone strony: 3 |
| WIM | oracle | 88 | 2 |  |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 0 | 0 | blokada Incapsula |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>26 paź · 01:30</b> · Zablokowany · oracle</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#64](https://github.com/kilerdevs/PlanWAT/actions/runs/40249645750), od planu do raportu 32 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, WIM, IOE, WCY, WML, WTC | 0 | 31 min, zablokowany na WLO, WML, WTC |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 3 | 0 | odrzucone strony: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 39 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

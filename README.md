# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 26 paź 2026 · 20:01 · **plebania** · **oracle** · 60 min · [przebieg #68](https://github.com/kilerdevs/PlanWAT/actions/runs/40382908076)
> Strona wydziału WML, WIM zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 9 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 26 paź · 20:01 | Zablokowany | **plebania** (WLO, WEL, WCY, WML, WIM (od oracle), WTC (od oracle)) · **oracle** (WIM, IOE, WTC, WML (od plebania)) | 485 | 60 min | [#68](https://github.com/kilerdevs/PlanWAT/actions/runs/40382908076) |
| 26 paź · 16:19 | Część stron odrzucona | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 110 | 10 min | [#67](https://github.com/kilerdevs/PlanWAT/actions/runs/40348126142) |
| 26 paź · 15:00 | Zmiany w 124 planach | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 735 | 41 min | [#66](https://github.com/kilerdevs/PlanWAT/actions/runs/40335568289) |
| 26 paź · 08:56 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC) · ~~plebania~~ | 261 | 55 min | [#65](https://github.com/kilerdevs/PlanWAT/actions/runs/40288910011) |
| 26 paź · 01:30 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC) · ~~plebania~~ | 42 | 32 min | [#64](https://github.com/kilerdevs/PlanWAT/actions/runs/40249645750) |
| 25 paź · 23:24 | Bez zmian | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 46 | 8 min | [#63](https://github.com/kilerdevs/PlanWAT/actions/runs/40240046249) |
| 25 paź · 22:56 | Bez zmian | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 68 | 14 min | [#62](https://github.com/kilerdevs/PlanWAT/actions/runs/40237831558) |
| 25 paź · 21:59 | Zablokowany | **plebania** (WLO, WEL, WCY, WML) · **oracle** (WIM, IOE, WTC) | 101 | 50 min | [#61](https://github.com/kilerdevs/PlanWAT/actions/runs/40233347824) |
| 25 paź · 21:46 | Zablokowany | **plebania** (WLO, WEL, WCY, WML) · **oracle** (WIM, IOE, WTC) | 654 | 37 min | [#60](https://github.com/kilerdevs/PlanWAT/actions/runs/40232365038) |

## Szczegóły

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

<details>
<summary><b>25 paź · 23:24</b> · Bez zmian · plebania · oracle</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg uruchomiony ręcznie [#63](https://github.com/kilerdevs/PlanWAT/actions/runs/40240046249), od planu do raportu 8 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 7 min |
| **oracle** | WIM, IOE, WTC | 0 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | <1 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| WCY | plebania | 39 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 3 | 0 | odrzucone strony: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | plebania | 1 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>25 paź · 22:56</b> · Bez zmian · plebania · oracle</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg uruchomiony ręcznie [#62](https://github.com/kilerdevs/PlanWAT/actions/runs/40237831558), od planu do raportu 14 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 9 min |
| **oracle** | WIM, IOE, WTC | 0 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | 4 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| WCY | plebania | 39 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 3 | 0 | odrzucone strony: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | plebania | 23 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |

</details>

<details>
<summary><b>25 paź · 21:59</b> · Zablokowany · plebania · oracle</summary>

Strona wydziału WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#61](https://github.com/kilerdevs/PlanWAT/actions/runs/40233347824), od planu do raportu 50 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 14 min |
| **oracle** | WIM, IOE, WTC | 0 | 31 min, zablokowany |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| WCY | plebania | 95 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 3 | 0 | odrzucone strony: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>25 paź · 21:46</b> · Zablokowany · plebania · oracle</summary>

Strona wydziału WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#60](https://github.com/kilerdevs/PlanWAT/actions/runs/40232365038), od planu do raportu 37 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 36 min |
| **oracle** | WIM, IOE, WTC | 0 | 31 min, zablokowany |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 |  |
| WEL | plebania | 158 | 0 | odrzucone strony: 3 |
| WCY | plebania | 100 | 0 | odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | plebania | 162 | 0 | odrzucone strony: 3 |
| WIM | oracle | 88 | 0 |  |
| IOE | oracle | 15 | 0 |  |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

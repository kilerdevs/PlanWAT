# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 1 lis 2026 · 00:29 · **oracle** · **northflank** · ~~plebania~~ · 25 min · [przebieg #101](https://github.com/kilerdevs/PlanWAT/actions/runs/41252748381)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 1 lis · 00:29 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 381 | 25 min | [#101](https://github.com/kilerdevs/PlanWAT/actions/runs/41252748381) |
| 31 paź · 19:39 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 430 | 28 min | [#100](https://github.com/kilerdevs/PlanWAT/actions/runs/41230469899) |
| 31 paź · 13:51 | Zmiana w 1 planie | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 594 | 23 min | [#99](https://github.com/kilerdevs/PlanWAT/actions/runs/41202942009) |
| 31 paź · 06:59 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 436 | 31 min | [#98](https://github.com/kilerdevs/PlanWAT/actions/runs/41174756159) |
| 31 paź · 00:55 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM) · ~~plebania~~ | 388 | 25 min | [#97](https://github.com/kilerdevs/PlanWAT/actions/runs/41147228375) |
| 30 paź · 20:31 | Część stron odrzucona | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 602 | 23 min | [#96](https://github.com/kilerdevs/PlanWAT/actions/runs/41115858859) |
| 30 paź · 14:14 | Zmiany w 53 planach | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 546 | 19 min | [#95](https://github.com/kilerdevs/PlanWAT/actions/runs/41061559545) |
| 30 paź · 07:05 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 368 | 26 min | [#94](https://github.com/kilerdevs/PlanWAT/actions/runs/41012019380) |
| 30 paź · 01:00 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 236 | 48 min | [#93](https://github.com/kilerdevs/PlanWAT/actions/runs/40976852727) |
| 29 paź · 20:44 | Niedokończony | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG, WCY (pomoc dla plebania)) · **northflank** (WIM) | 2 | 18 min | [#92](https://github.com/kilerdevs/PlanWAT/actions/runs/40942759019) |

## Szczegóły

<details>
<summary><b>1 lis · 00:29</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#101](https://github.com/kilerdevs/PlanWAT/actions/runs/41252748381), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 132 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 26 | 0 | z pomocą northflank |
| WIM | northflank | 49 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>31 paź · 19:39</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#100](https://github.com/kilerdevs/PlanWAT/actions/runs/41230469899), od planu do raportu 28 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 27 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 183 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 26 | 0 | z pomocą northflank |
| WIM | northflank | 47 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>31 paź · 13:51</b> · Zmiana w 1 planie · plebania · oracle · northflank</summary>

Pobrano nową wersję 1 planu. Przebieg automatyczny [#99](https://github.com/kilerdevs/PlanWAT/actions/runs/41202942009), od planu do raportu 23 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 0 | 22 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania) | 0 | 20 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 1 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 144 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 0 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 9 | 0 | z pomocą northflank |
| WCY | oracle | 69 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 18 | 0 | z pomocą northflank |
| WIM | northflank | 38 | 0 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>31 paź · 06:59</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#98](https://github.com/kilerdevs/PlanWAT/actions/runs/41174756159), od planu do raportu 31 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 5 | 30 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 183 | 5 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 27 | 0 | z pomocą northflank |
| WIM | northflank | 52 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>31 paź · 00:55</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#97](https://github.com/kilerdevs/PlanWAT/actions/runs/41147228375), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 9 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 3 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 132 | 9 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | northflank | 49 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>30 paź · 20:31</b> · Część stron odrzucona · plebania · oracle · northflank</summary>

Część stron nie przeszła kontroli, więc zostają dla nich poprzednie plany. Przebieg automatyczny [#96](https://github.com/kilerdevs/PlanWAT/actions/runs/41115858859), od planu do raportu 23 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle) | 8 | 16 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 0 | 14 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 3 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 5 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 91 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 8 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 11 | 0 | z pomocą northflank |
| WCY | oracle | 68 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 28 | 0 | z pomocą northflank |
| WIM | oracle | 88 | 0 | przejęty od northflank, który go nie skończył |

</details>

<details>
<summary><b>30 paź · 14:14</b> · Zmiany w 53 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 53 planów. Przebieg automatyczny [#95](https://github.com/kilerdevs/PlanWAT/actions/runs/41061559545), od planu do raportu 19 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 35 | 18 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania) | 13 | 14 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 5 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 8 | odrzucone strony: 1 |
| WEL | plebania | 99 | 7 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 8 |  |
| WTC | plebania | 23 | 6 |  |
| IOE | oracle | 10 | 3 | z pomocą northflank |
| WCY | oracle | 67 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 18 | 0 | z pomocą northflank |
| WIM | northflank | 36 | 5 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>30 paź · 07:05</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#94](https://github.com/kilerdevs/PlanWAT/actions/runs/41012019380), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 19 | 25 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 1 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 158 | 0 | odrzucone strony: 3 |
| IOE | oracle | 9 | 0 | z pomocą northflank |
| WCY | oracle | 131 | 19 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 20 | 0 | z pomocą northflank |
| WIM | northflank | 50 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>30 paź · 01:00</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#93](https://github.com/kilerdevs/PlanWAT/actions/runs/40976852727), od planu do raportu 48 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 11 | 47 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 158 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 0 | 0 | blokada Incapsula |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 18 | 0 | z pomocą northflank |
| WIM | northflank | 50 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>29 paź · 20:44</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WLO, WEL, WCY, WML, WTC). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#92](https://github.com/kilerdevs/PlanWAT/actions/runs/40942759019), od planu do raportu 18 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC | 0 | brak raportu |
| **oracle** | IOE, WIG, WCY (pomoc dla plebania) | 0 | 8 min |
| **northflank** | WIM | 0 | 2 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | – | – | brak danych z tego przebiegu |
| WEL | plebania | – | – | brak danych z tego przebiegu |
| WCY | plebania | – | – | z pomocą oracle, brak danych z tego przebiegu |
| WML | plebania | – | – | brak danych z tego przebiegu |
| WTC | plebania | – | – | brak danych z tego przebiegu |
| IOE | oracle | 2 | 0 |  |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 0 | 0 |  |

</details>

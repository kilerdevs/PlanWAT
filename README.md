# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 30 paź 2026 · 07:05 · **oracle** · **northflank** · ~~plebania~~ · 26 min · [przebieg #94](https://github.com/kilerdevs/PlanWAT/actions/runs/41012019380)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 30 paź · 07:05 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 368 | 26 min | [#94](https://github.com/kilerdevs/PlanWAT/actions/runs/41012019380) |
| 30 paź · 01:00 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 236 | 48 min | [#93](https://github.com/kilerdevs/PlanWAT/actions/runs/40976852727) |
| 29 paź · 20:44 | Niedokończony | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG, WCY (pomoc dla plebania)) · **northflank** (WIM) | 2 | 18 min | [#92](https://github.com/kilerdevs/PlanWAT/actions/runs/40942759019) |
| 29 paź · 18:20 | Zmiany w 46 planach | **plebania** (WLO, WEL, WCY, WML, WTC, WIM (pomoc dla northflank), IOE (pomoc dla oracle)) · **oracle** (IOE, WIG, WLO (pomoc dla plebania), WIM (pomoc dla northflank), WCY (pomoc dla plebania), WEL (pomoc dla plebania)) · **northflank** (WIM, WIG (pomoc dla oracle)) | 456 | 20 min | [#91](https://github.com/kilerdevs/PlanWAT/actions/runs/40920279500) |
| 29 paź · 14:24 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG) · **northflank** (WIM) · ~~plebania~~ | 105 | 26 min | [#90](https://github.com/kilerdevs/PlanWAT/actions/runs/40881542010) |
| 29 paź · 12:46 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 293 | 14 min | [#89](https://github.com/kilerdevs/PlanWAT/actions/runs/40868011435) |
| 29 paź · 07:04 | Zablokowany | **oracle** (WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank)) · **northflank** (WLO, WEL, WML, WIM (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 140 | 23 min | [#88](https://github.com/kilerdevs/PlanWAT/actions/runs/40826983483) |
| 28 paź · 23:43 | Zablokowany | **plebania** (WLO, WEL, WTC, WCY (od oracle)) · **oracle** (WIM, IOE, WCY, WIG) · **northflank** (WML) | 140 | 604 min | [#87](https://github.com/kilerdevs/PlanWAT/actions/runs/40782094339) |
| 28 paź · 23:19 | Niedokończony | **plebania** (WLO, WEL, WTC, IOE (pomoc dla oracle), WML (pomoc dla northflank), WIM (pomoc dla oracle), WIG (pomoc dla oracle), WCY (od oracle)) · **oracle** (WIM, IOE, WCY, WIG, WEL (pomoc dla northflank)) · **northflank** (WML, WIM (pomoc dla oracle), WEL (pomoc dla plebania)) | 203 | 47 min | [#86](https://github.com/kilerdevs/PlanWAT/actions/runs/40779074438) |
| 28 paź · 17:44 | Zablokowany | **plebania** (WLO, WEL, WCY, WTC) · **oracle** (WIM, IOE, WIG) · **northflank** (WML, WIM (pomoc dla oracle)) | 468 | 21 min | [#85](https://github.com/kilerdevs/PlanWAT/actions/runs/40728823148) |

## Szczegóły

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

<details>
<summary><b>29 paź · 18:20</b> · Zmiany w 46 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 46 planów. Przebieg uruchomiony ręcznie [#91](https://github.com/kilerdevs/PlanWAT/actions/runs/40920279500), od planu do raportu 20 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC, WIM (pomoc dla northflank), IOE (pomoc dla oracle) | 41 | 19 min |
| **oracle** | IOE, WIG, WLO (pomoc dla plebania), WIM (pomoc dla northflank), WCY (pomoc dla plebania), WEL (pomoc dla plebania) | 5 | 13 min |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 70 | 2 | z pomocą oracle, odrzucone strony: 1 |
| WEL | plebania | 83 | 3 | z pomocą oracle, odrzucone strony: 3 |
| WCY | plebania | 57 | 10 | z pomocą oracle, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | plebania | 162 | 24 |  |
| WTC | plebania | 23 | 2 |  |
| IOE | oracle | 9 | 2 | z pomocą plebania |
| WIG | oracle | 19 | 0 | z pomocą northflank |
| WIM | northflank | 33 | 0 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>29 paź · 14:24</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#90](https://github.com/kilerdevs/PlanWAT/actions/runs/40881542010), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 13 | 25 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM | 0 | 1 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 3 | 0 | odrzucone strony: 3 |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 92 | 13 | blokada Incapsula, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 10 | 0 |  |

</details>

<details>
<summary><b>29 paź · 12:46</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#89](https://github.com/kilerdevs/PlanWAT/actions/runs/40868011435), od planu do raportu 14 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 4 | 13 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 6 | 3 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 158 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 54 | 0 | blokada, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 20 | 0 | z pomocą northflank |
| WIM | northflank | 51 | 6 | z pomocą oracle |

</details>

<details>
<summary><b>29 paź · 07:04</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WCY, WTC, WLO, WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#88](https://github.com/kilerdevs/PlanWAT/actions/runs/40826983483), od planu do raportu 23 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank) | 0 | 22 min, zablokowany na WCY, WTC |
| **northflank** | WLO, WEL, WML, WIM (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 22 min, zablokowany na WLO, WML |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIM | oracle | 47 | 0 | z pomocą northflank |
| IOE | oracle | 11 | 0 | z pomocą northflank |
| WCY | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 29 | 0 | z pomocą northflank |
| WLO | northflank | 0 | 0 | blokada Incapsula |
| WEL | northflank | 53 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | northflank | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>28 paź · 23:43</b> · Zablokowany · plebania · oracle · northflank</summary>

Strona wydziału WLO, WTC, WCY, WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#87](https://github.com/kilerdevs/PlanWAT/actions/runs/40782094339), od planu do raportu 604 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WTC | 0 | 1 min |
| **oracle** | WIM, IOE, WCY, WIG | 0 | 2 min, niedokończony |
| **northflank** | WML | 0 | 1 min, zablokowany na WML |
| **plebania** (przejęcie) | WCY (od oracle) | 0 | brak raportu |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 | blokada Incapsula |
| WEL | plebania | 53 | 0 | odrzucone strony: 3 |
| WTC | plebania | 0 | 0 | blokada Incapsula |
| WIM | oracle | 47 | 0 |  |
| IOE | oracle | 11 | 0 |  |
| WCY | plebania | 0 | 0 | przejęty od oracle, który go nie skończył, blokada Incapsula |
| WIG | oracle | 29 | 0 |  |
| WML | northflank | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>28 paź · 23:19</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WCY). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg uruchomiony ręcznie [#86](https://github.com/kilerdevs/PlanWAT/actions/runs/40779074438), od planu do raportu 47 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WTC, IOE (pomoc dla oracle), WML (pomoc dla northflank), WIM (pomoc dla oracle), WIG (pomoc dla oracle) | 7 | 25 min |
| **oracle** | WIM, IOE, WCY, WIG, WEL (pomoc dla northflank) | 0 | 11 min, niedokończony |
| **northflank** | WML, WIM (pomoc dla oracle), WEL (pomoc dla plebania) | 1 | 12 min |
| **plebania** (przejęcie) | WCY (od oracle) | 0 | brak raportu |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 1 | 0 | odrzucone strony: 1 |
| WEL | plebania | 3 | 0 | z pomocą northflank, oracle, odrzucone strony: 3 |
| WTC | plebania | 0 | 0 |  |
| WIM | oracle | 17 | 0 | z pomocą northflank, plebania |
| IOE | oracle | 6 | 0 | z pomocą plebania |
| WCY | plebania | 0 | 0 | przejęty od oracle, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |
| WIG | oracle | 14 | 0 | z pomocą plebania |
| WML | northflank | 162 | 7 | z pomocą plebania |

</details>

<details>
<summary><b>28 paź · 17:44</b> · Zablokowany · plebania · oracle · northflank</summary>

Strona wydziału zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#85](https://github.com/kilerdevs/PlanWAT/actions/runs/40728823148), od planu do raportu 21 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WTC | 0 | 1 min, niedokończony |
| **oracle** | WIM, IOE, WIG | 0 | 2 min |
| **northflank** | WML, WIM (pomoc dla oracle) | 0 | 2 min, zablokowany na WML |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 27 | odrzucone strony: 1 |
| WEL | plebania | 73 | 2 | odrzucone strony: 3 |
| WCY | plebania | 83 | 1 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WTC | plebania | – | – | brak danych z tego przebiegu |
| WIM | oracle | 19 | 0 | z pomocą northflank |
| IOE | oracle | 0 | 0 |  |
| WIG | oracle | 0 | 0 |  |
| WML | northflank | 162 | 87 |  |

</details>

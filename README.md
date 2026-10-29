# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 29 paź 2026 · 07:04 · **oracle** · **northflank** · ~~plebania~~ · 23 min · [przebieg #88](https://github.com/kilerdevs/PlanWAT/actions/runs/40826983483)
> Strona wydziału WCY, WTC, WLO, WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 29 paź · 07:04 | Zablokowany | **oracle** (WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank)) · **northflank** (WLO, WEL, WML, WIM (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 140 | 23 min | [#88](https://github.com/kilerdevs/PlanWAT/actions/runs/40826983483) |
| 28 paź · 23:43 | Zablokowany | **plebania** (WLO, WEL, WTC, WCY (od oracle)) · **oracle** (WIM, IOE, WCY, WIG) · **northflank** (WML) | 140 | 604 min | [#87](https://github.com/kilerdevs/PlanWAT/actions/runs/40782094339) |
| 28 paź · 23:19 | Niedokończony | **plebania** (WLO, WEL, WTC, IOE (pomoc dla oracle), WML (pomoc dla northflank), WIM (pomoc dla oracle), WIG (pomoc dla oracle), WCY (od oracle)) · **oracle** (WIM, IOE, WCY, WIG, WEL (pomoc dla northflank)) · **northflank** (WML, WIM (pomoc dla oracle), WEL (pomoc dla plebania)) | 203 | 47 min | [#86](https://github.com/kilerdevs/PlanWAT/actions/runs/40779074438) |
| 28 paź · 17:44 | Zablokowany | **plebania** (WLO, WEL, WCY, WTC) · **oracle** (WIM, IOE, WIG) · **northflank** (WML, WIM (pomoc dla oracle)) | 468 | 21 min | [#85](https://github.com/kilerdevs/PlanWAT/actions/runs/40728823148) |
| 28 paź · 17:37 | Zmiany w 139 planach | **plebania** (WLO, WEL, WCY, WTC, WML (pomoc dla northflank), WIM (pomoc dla oracle)) · **oracle** (WIM, IOE, WIG, WCY (pomoc dla plebania), WEL (pomoc dla northflank)) · **northflank** (WML, IOE (pomoc dla oracle), WIM (pomoc dla oracle), WEL (pomoc dla plebania), WIG (pomoc dla oracle)) | 491 | 27 min | [#84](https://github.com/kilerdevs/PlanWAT/actions/runs/40727694805) |
| 28 paź · 09:44 | Zablokowany | **oracle** (WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank)) · **northflank** (WLO, WEL, WML, WIM (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 339 | 42 min | [#83](https://github.com/kilerdevs/PlanWAT/actions/runs/40659002362) |
| 28 paź · 02:29 | Zablokowany | **oracle** (WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank)) · **northflank** (WLO, WEL, WML) · ~~plebania~~ | 58 | 32 min | [#82](https://github.com/kilerdevs/PlanWAT/actions/runs/40615344614) |
| 27 paź · 23:56 | Zablokowany | **oracle** (WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank)) · **northflank** (WLO, WEL, WML, WIM (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 311 | 43 min | [#81](https://github.com/kilerdevs/PlanWAT/actions/runs/40598480384) |
| 27 paź · 21:51 | Zablokowany | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG, WLO (od plebania), WEL (od plebania), WML (od plebania), WTC (od plebania)) · **northflank** (WIM) | 81 | 17 min | [#80](https://github.com/kilerdevs/PlanWAT/actions/runs/40581697606) |
| 27 paź · 21:48 | Niedokończony | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG) · **northflank** (WIM) | 0 | 2 min | [#79](https://github.com/kilerdevs/PlanWAT/actions/runs/40581351708) |

## Szczegóły

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

<details>
<summary><b>28 paź · 17:37</b> · Zmiany w 139 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 139 planów. Przebieg uruchomiony ręcznie [#84](https://github.com/kilerdevs/PlanWAT/actions/runs/40727694805), od planu do raportu 27 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WTC, WML (pomoc dla northflank), WIM (pomoc dla oracle) | 118 | 26 min |
| **oracle** | WIM, IOE, WIG, WCY (pomoc dla plebania), WEL (pomoc dla northflank) | 15 | 11 min |
| **northflank** | WML, IOE (pomoc dla oracle), WIM (pomoc dla oracle), WEL (pomoc dla plebania), WIG (pomoc dla oracle) | 6 | 10 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 27 | odrzucone strony: 1 |
| WEL | plebania | 73 | 2 | z pomocą northflank, oracle, odrzucone strony: 3 |
| WCY | plebania | 83 | 1 | z pomocą oracle, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WTC | plebania | 23 | 3 |  |
| WIM | oracle | 19 | 0 | z pomocą northflank, plebania |
| IOE | oracle | 0 | 0 | z pomocą northflank |
| WIG | oracle | 0 | 0 | z pomocą northflank |
| WML | northflank | 162 | 87 | z pomocą plebania |

</details>

<details>
<summary><b>28 paź · 09:44</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WTC, WLO, WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#83](https://github.com/kilerdevs/PlanWAT/actions/runs/40659002362), od planu do raportu 42 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank) | 5 | 27 min, zablokowany na WTC |
| **northflank** | WLO, WEL, WML, WIM (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 1 | 41 min, zablokowany na WLO, WML |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIM | oracle | 47 | 1 | z pomocą northflank |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 182 | 4 | odrzucone strony: 2, bez planu na ten semestr: 51 |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 28 | 0 | z pomocą northflank |
| WLO | northflank | 0 | 0 | blokada Incapsula |
| WEL | northflank | 72 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | northflank | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>28 paź · 02:29</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WTC, WLO, WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#82](https://github.com/kilerdevs/PlanWAT/actions/runs/40615344614), od planu do raportu 32 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank) | 9 | 9 min, zablokowany na WTC |
| **northflank** | WLO, WEL, WML | 0 | 31 min, zablokowany na WLO, WML |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIM | oracle | 1 | 0 |  |
| IOE | oracle | 2 | 1 |  |
| WCY | oracle | 43 | 8 | odrzucone strony: 2, bez planu na ten semestr: 51 |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |
| WLO | northflank | 0 | 0 | blokada Incapsula |
| WEL | northflank | 12 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | northflank | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>27 paź · 23:56</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WTC, WLO zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#81](https://github.com/kilerdevs/PlanWAT/actions/runs/40598480384), od planu do raportu 43 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WIM, IOE, WCY, WTC, WIG, WEL (pomoc dla northflank) | 2 | 42 min, zablokowany na WTC |
| **northflank** | WLO, WEL, WML, WIM (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 41 min, zablokowany na WLO |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIM | oracle | 48 | 0 | z pomocą northflank |
| IOE | oracle | 15 | 2 |  |
| WCY | oracle | 150 | 0 | odrzucone strony: 2, bez planu na ten semestr: 51 |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 26 | 0 | z pomocą northflank |
| WLO | northflank | 0 | 0 | blokada Incapsula |
| WEL | northflank | 72 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | northflank | 0 | 0 | nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>27 paź · 21:51</b> · Zablokowany · plebania · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#80](https://github.com/kilerdevs/PlanWAT/actions/runs/40581697606), od planu do raportu 17 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC | 8 | 12 min, zablokowany na WLO, WEL, WML, WTC |
| **oracle** | IOE, WIG | 0 | 1 min |
| **northflank** | WIM | 0 | 2 min |
| **oracle** (przejęcie) | WLO (od plebania), WEL (od plebania), WML (od plebania), WTC (od plebania) | 0 | 4 min, zablokowany na WLO, WML, WTC |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | przejęty po blokadzie na plebania, blokada Incapsula |
| WEL | oracle | 21 | 0 | przejęty po blokadzie na plebania, odrzucone strony: 3 |
| WCY | plebania | 54 | 8 | odrzucone strony: 2, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | przejęty po blokadzie na plebania, blokada Incapsula |
| WTC | oracle | 0 | 0 | przejęty po blokadzie na plebania, blokada Incapsula |
| IOE | oracle | 1 | 0 |  |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 5 | 0 |  |

</details>

<details>
<summary><b>27 paź · 21:48</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WLO, WEL, WCY, WML, WTC, IOE, WIG, WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#79](https://github.com/kilerdevs/PlanWAT/actions/runs/40581351708), od planu do raportu 2 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC | 0 | 1 min, niedokończony |
| **oracle** | IOE, WIG | 0 | 1 min, niedokończony |
| **northflank** | WIM | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | – | – | brak danych z tego przebiegu |
| WEL | plebania | – | – | brak danych z tego przebiegu |
| WCY | plebania | – | – | brak danych z tego przebiegu |
| WML | plebania | – | – | brak danych z tego przebiegu |
| WTC | plebania | – | – | brak danych z tego przebiegu |
| IOE | oracle | – | – | brak danych z tego przebiegu |
| WIG | oracle | – | – | brak danych z tego przebiegu |
| WIM | northflank | – | – | brak danych z tego przebiegu |

</details>

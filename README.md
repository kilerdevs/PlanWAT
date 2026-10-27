# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 27 paź 2026 · 21:51 · **plebania** · **oracle** · **northflank** · 17 min · [przebieg #80](https://github.com/kilerdevs/PlanWAT/actions/runs/40581697606)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 27 paź · 21:51 | Zablokowany | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG, WLO (od plebania), WEL (od plebania), WML (od plebania), WTC (od plebania)) · **northflank** (WIM) | 81 | 17 min | [#80](https://github.com/kilerdevs/PlanWAT/actions/runs/40581697606) |
| 27 paź · 21:48 | Niedokończony | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (IOE, WIG) · **northflank** (WIM) | 0 | 2 min | [#79](https://github.com/kilerdevs/PlanWAT/actions/runs/40581351708) |
| 27 paź · 19:24 | Zablokowany | **plebania** (WLO, WEL, WCY, WML, WTC, WIM (pomoc dla northflank), WIG (pomoc dla oracle)) · **oracle** (IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla northflank), WCY (pomoc dla plebania), WML (od plebania)) · **northflank** (WIM) | 504 | 34 min | [#78](https://github.com/kilerdevs/PlanWAT/actions/runs/40559688724) |
| 27 paź · 15:42 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM) · ~~plebania~~ | 70 | 33 min | [#77](https://github.com/kilerdevs/PlanWAT/actions/runs/40523688285) |
| 27 paź · 14:22 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM) · ~~plebania~~ | 90 | 38 min | [#76](https://github.com/kilerdevs/PlanWAT/actions/runs/40511393088) |
| 27 paź · 13:20 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG) · **northflank** (WIM) · ~~plebania~~ | 166 | 49 min | [#75](https://github.com/kilerdevs/PlanWAT/actions/runs/40502995262) |
| 27 paź · 12:49 | Niedokończony | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG) · **northflank** (WIM) · ~~plebania~~ | 0 | 16 min | [#74](https://github.com/kilerdevs/PlanWAT/actions/runs/40499062574) |
| 27 paź · 09:03 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG) · ~~plebania~~ | 349 | 55 min | [#73](https://github.com/kilerdevs/PlanWAT/actions/runs/40470944765) |
| 27 paź · 02:32 | Zablokowany | **oracle** (WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG) · ~~plebania~~ | 393 | 48 min | [#72](https://github.com/kilerdevs/PlanWAT/actions/runs/40433154047) |
| 27 paź · 00:00 | Bez zmian | **plebania** (WLO, WEL, WCY, WML, WTC) · **oracle** (WIM, IOE, WIG) | 126 | 11 min | [#71](https://github.com/kilerdevs/PlanWAT/actions/runs/40416669173) |

## Szczegóły

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

<details>
<summary><b>27 paź · 19:24</b> · Zablokowany · plebania · oracle · northflank</summary>

Strona wydziału WML zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#78](https://github.com/kilerdevs/PlanWAT/actions/runs/40559688724), od planu do raportu 34 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML, WTC, WIM (pomoc dla northflank), WIG (pomoc dla oracle) | 29 | 32 min, zablokowany na WML |
| **oracle** | IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla northflank), WCY (pomoc dla plebania) | 18 | 26 min |
| **northflank** | WIM | 2 | 4 min |
| **oracle** (przejęcie) | WML (od plebania) | 0 | 1 min, zablokowany na WML |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 19 |  |
| WEL | plebania | 134 | 16 | z pomocą oracle, odrzucone strony: 3 |
| WCY | plebania | 148 | 0 | z pomocą oracle, odrzucone strony: 1, bez planu na ten semestr: 76 |
| WML | oracle | 0 | 0 | przejęty po blokadzie na plebania, blokada Incapsula |
| WTC | plebania | 23 | 7 | odrzucone strony: 1 |
| IOE | oracle | 15 | 1 |  |
| WIG | oracle | 25 | 0 | z pomocą plebania |
| WIM | northflank | 28 | 2 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>27 paź · 15:42</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#77](https://github.com/kilerdevs/PlanWAT/actions/runs/40523688285), od planu do raportu 33 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 2 | 32 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM | 0 | 2 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 3 | 0 | odrzucone strony: 3 |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 53 | 1 | blokada Incapsula, odrzucone strony: 1, bez planu na ten semestr: 38 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 14 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>27 paź · 14:22</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#76](https://github.com/kilerdevs/PlanWAT/actions/runs/40511393088), od planu do raportu 38 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 10 | 37 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM | 10 | 5 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 43 | 0 | odrzucone strony: 3 |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 0 | 0 | blokada Incapsula |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 47 | 10 | z pomocą oracle |

</details>

<details>
<summary><b>27 paź · 13:20</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#75](https://github.com/kilerdevs/PlanWAT/actions/runs/40502995262), od planu do raportu 49 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 48 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM | 0 | 48 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 118 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 0 | 0 | blokada Incapsula |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | northflank | – | – | brak danych z tego przebiegu |

</details>

<details>
<summary><b>27 paź · 12:49</b> · Niedokończony · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg uruchomiony ręcznie [#74](https://github.com/kilerdevs/PlanWAT/actions/runs/40499062574), od planu do raportu 16 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 15 min, niedokończony |
| **northflank** | WIM | 0 | brak raportu |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | – | – | brak danych z tego przebiegu |
| WEL | oracle | – | – | brak danych z tego przebiegu |
| IOE | oracle | – | – | brak danych z tego przebiegu |
| WCY | oracle | – | – | brak danych z tego przebiegu |
| WML | oracle | – | – | brak danych z tego przebiegu |
| WTC | oracle | – | – | brak danych z tego przebiegu |
| WIG | oracle | – | – | brak danych z tego przebiegu |
| WIM | northflank | – | – | brak danych z tego przebiegu |

</details>

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

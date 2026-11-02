# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 2 lis 2026 · 02:37 · **oracle** · **northflank** · ~~plebania~~ · 24 min · [przebieg #106](https://github.com/kilerdevs/PlanWAT/actions/runs/41373405256)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 2 lis · 02:37 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 418 | 24 min | [#106](https://github.com/kilerdevs/PlanWAT/actions/runs/41373405256) |
| 1 lis · 21:38 | Bez zmian | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · **plebania** (WLO (od oracle), WML (od oracle), WTC (od oracle)) · ~~plebania~~ | 687 | 48 min | [#105](https://github.com/kilerdevs/PlanWAT/actions/runs/41347909263) |
| 1 lis · 16:20 | Bez zmian | **plebania** (WLO, WEL, WML, WTC) · **oracle** (IOE, WCY, WIG) · **northflank** (WIM) | 9 | 2 min | [#104](https://github.com/kilerdevs/PlanWAT/actions/runs/41320677165) |
| 1 lis · 14:15 | Zmiany w 4 planach | **plebania** (WLO, WEL, WML, WTC, IOE (pomoc dla oracle), WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla plebania), WEL (pomoc dla plebania)) · **northflank** (WIM, WIG (pomoc dla oracle)) | 615 | 24 min | [#103](https://github.com/kilerdevs/PlanWAT/actions/runs/41310391930) |
| 1 lis · 07:28 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle)) · ~~plebania~~ | 251 | 24 min | [#102](https://github.com/kilerdevs/PlanWAT/actions/runs/41280989625) |
| 1 lis · 00:29 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 381 | 25 min | [#101](https://github.com/kilerdevs/PlanWAT/actions/runs/41252748381) |
| 31 paź · 19:39 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 430 | 28 min | [#100](https://github.com/kilerdevs/PlanWAT/actions/runs/41230469899) |
| 31 paź · 13:51 | Zmiana w 1 planie | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 594 | 23 min | [#99](https://github.com/kilerdevs/PlanWAT/actions/runs/41202942009) |
| 31 paź · 06:59 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 436 | 31 min | [#98](https://github.com/kilerdevs/PlanWAT/actions/runs/41174756159) |
| 31 paź · 00:55 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM) · ~~plebania~~ | 388 | 25 min | [#97](https://github.com/kilerdevs/PlanWAT/actions/runs/41147228375) |

## Szczegóły

<details>
<summary><b>2 lis · 02:37</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#106](https://github.com/kilerdevs/PlanWAT/actions/runs/41373405256), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 23 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 183 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 19 | 0 | z pomocą northflank |
| WIM | northflank | 47 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>1 lis · 21:38</b> · Bez zmian · oracle · northflank · plebania</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg automatyczny [#105](https://github.com/kilerdevs/PlanWAT/actions/runs/41347909263), od planu do raportu 48 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 23 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 4 min |
| **plebania** (przejęcie) | WLO (od oracle), WML (od oracle), WTC (od oracle) | 0 | 24 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | przejęty po blokadzie na oracle, odrzucone strony: 1 |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 132 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | plebania | 162 | 0 | przejęty po blokadzie na oracle |
| WTC | plebania | 23 | 0 | przejęty po blokadzie na oracle |
| WIG | oracle | 21 | 0 | z pomocą northflank |
| WIM | northflank | 49 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>1 lis · 16:20</b> · Bez zmian · plebania · oracle · northflank</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg automatyczny [#104](https://github.com/kilerdevs/PlanWAT/actions/runs/41320677165), od planu do raportu 2 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC | 0 | 1 min |
| **oracle** | IOE, WCY, WIG | 0 | 2 min |
| **northflank** | WIM | 0 | 1 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 1 | 0 | odrzucone strony: 1 |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| WML | plebania | 0 | 0 |  |
| WTC | plebania | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 5 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 0 | 0 |  |

</details>

<details>
<summary><b>1 lis · 14:15</b> · Zmiany w 4 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 4 planów. Przebieg uruchomiony ręcznie [#103](https://github.com/kilerdevs/PlanWAT/actions/runs/41310391930), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, IOE (pomoc dla oracle), WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 4 | 23 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla plebania), WEL (pomoc dla plebania) | 0 | 20 min |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 148 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 0 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 9 | 0 | z pomocą plebania |
| WCY | oracle | 77 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 28 | 0 | z pomocą northflank |
| WIM | northflank | 37 | 0 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>1 lis · 07:28</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#102](https://github.com/kilerdevs/PlanWAT/actions/runs/41280989625), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 23 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle) | 0 | 3 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 159 | 0 | odrzucone strony: 3 |
| IOE | oracle | 11 | 0 | z pomocą northflank |
| WCY | oracle | 0 | 0 | nie udało się pobrać listy grup, lista grup podejrzanie krótka |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | northflank | 48 | 0 | z pomocą oracle |

</details>

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

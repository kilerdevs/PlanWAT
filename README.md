# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 8 lis 2026 · 02:35 · **oracle** · **northflank** · ~~plebania~~ · 4 min · [przebieg #127](https://github.com/kilerdevs/PlanWAT/actions/runs/42434920891)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 8 lis · 02:35 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 4 | 4 min | [#127](https://github.com/kilerdevs/PlanWAT/actions/runs/42434920891) |
| 7 lis · 23:05 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 323 | 26 min | [#126](https://github.com/kilerdevs/PlanWAT/actions/runs/42418928443) |
| 7 lis · 17:33 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 388 | 26 min | [#125](https://github.com/kilerdevs/PlanWAT/actions/runs/42391875222) |
| 7 lis · 09:58 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 342 | 26 min | [#124](https://github.com/kilerdevs/PlanWAT/actions/runs/42357677212) |
| 7 lis · 03:04 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 342 | 26 min | [#123](https://github.com/kilerdevs/PlanWAT/actions/runs/42327318306) |
| 6 lis · 22:39 | Niedokończony | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM) | 596 | 25 min | [#122](https://github.com/kilerdevs/PlanWAT/actions/runs/42298561749) |
| 6 lis · 17:02 | Niedokończony | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM) | 563 | 26 min | [#121](https://github.com/kilerdevs/PlanWAT/actions/runs/42248600516) |
| 6 lis · 08:04 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 388 | 26 min | [#120](https://github.com/kilerdevs/PlanWAT/actions/runs/42178421297) |
| 6 lis · 00:44 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 333 | 26 min | [#119](https://github.com/kilerdevs/PlanWAT/actions/runs/42131709133) |
| 5 lis · 17:35 | Niedokończony | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM) | 575 | 27 min | [#118](https://github.com/kilerdevs/PlanWAT/actions/runs/42066021855) |

## Szczegóły

<details>
<summary><b>8 lis · 02:35</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#127](https://github.com/kilerdevs/PlanWAT/actions/runs/42434920891), od planu do raportu 4 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 2 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 3 | 0 | odrzucone strony: 3 |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 1 | 0 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>7 lis · 23:05</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#126](https://github.com/kilerdevs/PlanWAT/actions/runs/42418928443), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 2 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 11 | 0 | z pomocą northflank |
| WCY | oracle | 134 | 0 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 18 | 0 | z pomocą northflank |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>7 lis · 17:33</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#125](https://github.com/kilerdevs/PlanWAT/actions/runs/42391875222), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 180 | 0 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>7 lis · 09:58</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#124](https://github.com/kilerdevs/PlanWAT/actions/runs/42357677212), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 134 | 0 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>7 lis · 03:04</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#123](https://github.com/kilerdevs/PlanWAT/actions/runs/42327318306), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 29 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 134 | 29 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>6 lis · 22:39</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#122](https://github.com/kilerdevs/PlanWAT/actions/runs/42298561749), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle), IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 4 | 22 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 0 | 18 min |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 140 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 4 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 11 | 0 | z pomocą plebania |
| WCY | oracle | 108 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 46 |
| WIG | oracle | 21 | 0 | z pomocą plebania |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>6 lis · 17:02</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#121](https://github.com/kilerdevs/PlanWAT/actions/runs/42248600516), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle) | 25 | 24 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 4 | 20 min |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 12 | odrzucone strony: 1 |
| WEL | plebania | 139 | 3 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 9 | odrzucone strony: 3 |
| WTC | plebania | 23 | 3 |  |
| IOE | oracle | 15 | 1 |  |
| WCY | oracle | 65 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 46 |
| WIG | oracle | 28 | 0 | z pomocą plebania |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>6 lis · 08:04</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#120](https://github.com/kilerdevs/PlanWAT/actions/runs/42178421297), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 6 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 1 |  |
| WCY | oracle | 180 | 5 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>6 lis · 00:44</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#119](https://github.com/kilerdevs/PlanWAT/actions/runs/42131709133), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 4 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 3 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 132 | 4 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 26 | 0 | z pomocą northflank |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>5 lis · 17:35</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#118](https://github.com/kilerdevs/PlanWAT/actions/runs/42066021855), od planu do raportu 27 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle) | 143 | 25 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 11 | 20 min |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 54 | odrzucone strony: 1 |
| WEL | plebania | 141 | 10 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 83 | odrzucone strony: 3 |
| WTC | plebania | 23 | 3 |  |
| IOE | oracle | 15 | 1 |  |
| WCY | oracle | 76 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 46 |
| WIG | oracle | 27 | 0 | z pomocą plebania |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

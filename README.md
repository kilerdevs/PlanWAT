# Odświeżanie planów: ostatnie przebiegi

> [!TIP]
> **Ostatni przebieg: zmiany w 74 planach.** 9 lis 2026 · 21:52 · **plebania** · **oracle** · **northflank** · 25 min · [przebieg #135](https://github.com/kilerdevs/PlanWAT/actions/runs/42697083344)
> Pobrano nowe wersje 74 planów.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 9 lis · 21:52 | Zmiany w 74 planach | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 629 | 25 min | [#135](https://github.com/kilerdevs/PlanWAT/actions/runs/42697083344) |
| 9 lis · 14:44 | Zmiany w 25 planach | **northflank** (WIM) · ~~plebania~~ | 88 | 6 min | [#134](https://github.com/kilerdevs/PlanWAT/actions/runs/42628054022) |
| 9 lis · 10:57 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 297 | 38 min | [#133](https://github.com/kilerdevs/PlanWAT/actions/runs/42597342737) |
| 9 lis · 02:48 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 4 | 4 min | [#132](https://github.com/kilerdevs/PlanWAT/actions/runs/42547453447) |
| 8 lis · 23:18 | Niedokończony | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM) | 208 | 12 min | [#131](https://github.com/kilerdevs/PlanWAT/actions/runs/42529555555) |
| 8 lis · 20:24 | Niedokończony | **plebania** (WLO, WEL, WML, WTC) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (od northflank)) · **northflank** (WIM) | 320 | 26 min | [#130](https://github.com/kilerdevs/PlanWAT/actions/runs/42514885892) |
| 8 lis · 17:44 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 342 | 26 min | [#129](https://github.com/kilerdevs/PlanWAT/actions/runs/42501384724) |
| 8 lis · 10:15 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 388 | 26 min | [#128](https://github.com/kilerdevs/PlanWAT/actions/runs/42466383970) |
| 8 lis · 02:35 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 4 | 4 min | [#127](https://github.com/kilerdevs/PlanWAT/actions/runs/42434920891) |
| 7 lis · 23:05 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 323 | 26 min | [#126](https://github.com/kilerdevs/PlanWAT/actions/runs/42418928443) |

## Szczegóły

<details>
<summary><b>9 lis · 21:52</b> · Zmiany w 74 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 74 planów. Przebieg automatyczny [#135](https://github.com/kilerdevs/PlanWAT/actions/runs/42697083344), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 58 | 24 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania) | 15 | 20 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 1 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 19 | odrzucone strony: 1 |
| WEL | plebania | 143 | 9 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 30 |  |
| WTC | plebania | 23 | 7 |  |
| IOE | oracle | 11 | 4 | z pomocą northflank |
| WCY | oracle | 97 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 28 | 0 | z pomocą northflank |
| WIM | northflank | 34 | 0 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>9 lis · 14:44</b> · Zmiany w 25 planach · northflank</summary>

Pobrano nowe wersje 25 planów. Przebieg uruchomiony ręcznie [#134](https://github.com/kilerdevs/PlanWAT/actions/runs/42628054022), od planu do raportu 6 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **northflank** | WIM | 25 | 5 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WIM | northflank | 88 | 25 |  |

</details>

<details>
<summary><b>9 lis · 10:57</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#133](https://github.com/kilerdevs/PlanWAT/actions/runs/42597342737), od planu do raportu 38 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG | 0 | 33 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 89 | 0 | blokada, odrzucone strony: 1, bez planu na ten semestr: 46 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>9 lis · 02:48</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#132](https://github.com/kilerdevs/PlanWAT/actions/runs/42547453447), od planu do raportu 4 min.

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
<summary><b>8 lis · 23:18</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg automatyczny [#131](https://github.com/kilerdevs/PlanWAT/actions/runs/42529555555), od planu do raportu 12 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 10 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 0 | 10 min |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 1 | 0 | odrzucone strony: 1 |
| WEL | plebania | 85 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 4 | 0 |  |
| WTC | plebania | 0 | 0 |  |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 77 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 46 |
| WIG | oracle | 26 | 0 | z pomocą plebania |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>8 lis · 20:24</b> · Niedokończony · plebania · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WIM). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg uruchomiony ręcznie [#130](https://github.com/kilerdevs/PlanWAT/actions/runs/42514885892), od planu do raportu 26 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC | 0 | 23 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania) | 0 | 2 min |
| **northflank** | WIM | 0 | 1 min, niedokończony |
| **oracle** (przejęcie) | WIM (od northflank) | 0 | 1 min, niedokończony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 3 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 0 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 1 | 0 | odrzucone strony: 1, bez planu na ten semestr: 46 |
| WIG | oracle | 0 | 0 |  |
| WIM | oracle | 0 | 0 | przejęty od northflank, który go nie skończył, nie udało się pobrać listy grup, lista grup podejrzanie krótka |

</details>

<details>
<summary><b>8 lis · 17:44</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#129](https://github.com/kilerdevs/PlanWAT/actions/runs/42501384724), od planu do raportu 26 min.

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
<summary><b>8 lis · 10:15</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#128](https://github.com/kilerdevs/PlanWAT/actions/runs/42466383970), od planu do raportu 26 min.

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

# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 11 lis 2026 · 10:38 · **oracle** · **northflank** · ~~plebania~~ · 25 min · [przebieg #142](https://github.com/kilerdevs/PlanWAT/actions/runs/42996902132)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 11 lis · 10:38 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 388 | 25 min | [#142](https://github.com/kilerdevs/PlanWAT/actions/runs/42996902132) |
| 11 lis · 03:00 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · ~~plebania~~ | 413 | 47 min | [#141](https://github.com/kilerdevs/PlanWAT/actions/runs/42942896941) |
| 10 lis · 21:55 | Zmiany w 62 planach | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 570 | 20 min | [#140](https://github.com/kilerdevs/PlanWAT/actions/runs/42899956684) |
| 10 lis · 13:49 | Zmiana w 1 planie | **plebania** (WLO, WEL, WML, WTC, WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM) | 76 | 6 min | [#139](https://github.com/kilerdevs/PlanWAT/actions/runs/42818985308) |
| 10 lis · 13:26 | Część stron odrzucona | **plebania** (WCY, WEL, WIM, WLO, WML, WTC, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla plebania), WCY (pomoc dla plebania)) · **northflank** (WIM (pomoc dla plebania), WIG (pomoc dla oracle)) | 798 | 25 min | [#138](https://github.com/kilerdevs/PlanWAT/actions/runs/42815694094) |
| 10 lis · 09:11 | Zablokowany | **oracle** (IOE, WCY, WEL, WIG) · **northflank** (WIM) · ~~plebania~~ | 49 | 5 min | [#137](https://github.com/kilerdevs/PlanWAT/actions/runs/42780716506) |
| 10 lis · 05:12 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 388 | 24 min | [#136](https://github.com/kilerdevs/PlanWAT/actions/runs/42754337287) |
| 9 lis · 21:52 | Zmiany w 74 planach | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 629 | 25 min | [#135](https://github.com/kilerdevs/PlanWAT/actions/runs/42697083344) |
| 9 lis · 14:44 | Zmiany w 25 planach | **northflank** (WIM) · ~~plebania~~ | 88 | 6 min | [#134](https://github.com/kilerdevs/PlanWAT/actions/runs/42628054022) |
| 9 lis · 10:57 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (od northflank)) · **northflank** (WIM) · ~~plebania~~ | 297 | 38 min | [#133](https://github.com/kilerdevs/PlanWAT/actions/runs/42597342737) |

## Szczegóły

<details>
<summary><b>11 lis · 10:38</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#142](https://github.com/kilerdevs/PlanWAT/actions/runs/42996902132), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 1 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 135 | 1 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 27 | 0 | z pomocą northflank |
| WIM | northflank | 51 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>11 lis · 03:00</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#141](https://github.com/kilerdevs/PlanWAT/actions/runs/42942896941), od planu do raportu 47 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 14 | 46 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 176 | 14 | blokada, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 19 | 0 | z pomocą northflank |
| WIM | northflank | 48 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>10 lis · 21:55</b> · Zmiany w 62 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 62 planów. Przebieg automatyczny [#140](https://github.com/kilerdevs/PlanWAT/actions/runs/42899956684), od planu do raportu 20 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 35 | 19 min |
| **oracle** | IOE, WCY, WIG, WEL (pomoc dla plebania), WIM (pomoc dla northflank) | 17 | 16 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 10 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 12 | odrzucone strony: 1 |
| WEL | plebania | 123 | 13 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 2 |  |
| WTC | plebania | 23 | 8 |  |
| IOE | oracle | 10 | 1 | z pomocą northflank |
| WCY | oracle | 70 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 19 | 0 | z pomocą northflank |
| WIM | northflank | 32 | 9 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>10 lis · 13:49</b> · Zmiana w 1 planie · plebania · oracle · northflank</summary>

Pobrano nową wersję 1 planu. Przebieg automatyczny [#139](https://github.com/kilerdevs/PlanWAT/actions/runs/42818985308), od planu do raportu 6 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WCY (pomoc dla oracle) | 0 | 4 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla northflank) | 1 | 5 min |
| **northflank** | WIM | 0 | 2 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 1 | 0 | odrzucone strony: 1 |
| WEL | plebania | 3 | 0 | odrzucone strony: 3 |
| WML | plebania | 0 | 0 |  |
| WTC | plebania | 0 | 0 |  |
| IOE | oracle | 7 | 1 |  |
| WCY | oracle | 35 | 0 | z pomocą plebania, bez planu na ten semestr: 35 |
| WIG | oracle | 9 | 0 |  |
| WIM | northflank | 21 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>10 lis · 13:26</b> · Część stron odrzucona · plebania · oracle · northflank</summary>

Część stron (WEL) nie przeszła kontroli, więc zostają dla nich poprzednie plany. Przebieg uruchomiony ręcznie [#138](https://github.com/kilerdevs/PlanWAT/actions/runs/42815694094), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WCY, WEL, WIM, WLO, WML, WTC, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 8 | 25 min, odrzucone strony na WEL |
| **oracle** | IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla plebania), WCY (pomoc dla plebania) | 2 | 21 min, zablokowany na WTC, WML |
| **northflank** | WIM (pomoc dla plebania), WIG (pomoc dla oracle) | 0 | 4 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 160 | 0 | z pomocą oracle, odrzucone strony: 3 z 160 |
| WIM | plebania | 88 | 0 | z pomocą oracle, northflank |
| IOE | oracle | 15 | 3 | z pomocą plebania |
| WCY | plebania | 186 | 0 | z pomocą oracle, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | plebania | 162 | 7 |  |
| WTC | plebania | 23 | 0 |  |
| WIG | oracle | 33 | 0 | z pomocą northflank, plebania |

</details>

<details>
<summary><b>10 lis · 09:11</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#137](https://github.com/kilerdevs/PlanWAT/actions/runs/42780716506), od planu do raportu 5 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG | 0 | 5 min, zablokowany na WTC, WML, WLO |
| **northflank** | WIM | 0 | 2 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO |  | 0 | 0 | blokada Incapsula |
| WEL | oracle | 14 | 0 | odrzucone strony: 3 z 14 |
| WIM | northflank | 2 | 0 |  |
| IOE | oracle | 5 | 0 |  |
| WCY | oracle | 28 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML |  | 0 | 0 | blokada Incapsula |
| WTC |  | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |

</details>

<details>
<summary><b>10 lis · 05:12</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#136](https://github.com/kilerdevs/PlanWAT/actions/runs/42754337287), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 27 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 135 | 27 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 27 | 0 | z pomocą northflank |
| WIM | northflank | 51 | 0 | z pomocą oracle |

</details>

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

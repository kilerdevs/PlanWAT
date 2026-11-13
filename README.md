# Odświeżanie planów: ostatnie przebiegi

> [!CAUTION]
> **Ostatni przebieg: zablokowany.** 13 lis 2026 · 19:31 · **oracle** · **northflank** · ~~plebania~~ · 11 min · [przebieg #151](https://github.com/kilerdevs/PlanWAT/actions/runs/43483477086)
> Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 13 lis · 19:31 | Zablokowany | **oracle** (IOE, WCY, WEL, WIG) · **northflank** (WIM) · ~~plebania~~ | 4 | 11 min | [#151](https://github.com/kilerdevs/PlanWAT/actions/runs/43483477086) |
| 13 lis · 18:55 | Bez zmian | **plebania** (WLO, WEL, WML, WTC) · **oracle** (IOE, WCY, WIG) · **northflank** (WIM) | 5 | 19 min | [#150](https://github.com/kilerdevs/PlanWAT/actions/runs/43477538480) |
| 13 lis · 18:52 | Część stron odrzucona | **plebania** (WCY, WEL, WIM, WLO, WML, WTC, WIG (pomoc dla oracle)) · **oracle** (IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla plebania), WCY (pomoc dla plebania)) · **northflank** (WIM (pomoc dla plebania), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 798 | 20 min | [#149](https://github.com/kilerdevs/PlanWAT/actions/runs/43476965918) |
| 13 lis · 10:46 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 300 | 36 min | [#148](https://github.com/kilerdevs/PlanWAT/actions/runs/43404099643) |
| 13 lis · 02:15 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, IOE (pomoc dla oracle)) · ~~plebania~~ | 441 | 24 min | [#147](https://github.com/kilerdevs/PlanWAT/actions/runs/43343452080) |
| 12 lis · 19:28 | Zmiany w 38 planach | **plebania** (WLO, WEL, WML, WTC, IOE (pomoc dla oracle), WIM (pomoc dla northflank), WCY (pomoc dla oracle), WIG (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla plebania), WEL (pomoc dla plebania)) · **northflank** (WIM, WIG (pomoc dla oracle)) | 592 | 24 min | [#146](https://github.com/kilerdevs/PlanWAT/actions/runs/43280095510) |
| 12 lis · 10:58 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 442 | 25 min | [#145](https://github.com/kilerdevs/PlanWAT/actions/runs/43196162350) |
| 12 lis · 01:53 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 387 | 25 min | [#144](https://github.com/kilerdevs/PlanWAT/actions/runs/43130531590) |
| 11 lis · 18:57 | Zmiany w 2 planach | **plebania** (WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle)) · **oracle** (IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania)) · **northflank** (WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 626 | 24 min | [#143](https://github.com/kilerdevs/PlanWAT/actions/runs/43073051284) |
| 11 lis · 10:38 | Zablokowany | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 388 | 25 min | [#142](https://github.com/kilerdevs/PlanWAT/actions/runs/42996902132) |

## Szczegóły

<details>
<summary><b>13 lis · 19:31</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#151](https://github.com/kilerdevs/PlanWAT/actions/runs/43483477086), od planu do raportu 11 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG | 0 | 10 min, zablokowany na WTC, WML, WLO |
| **northflank** | WIM | 0 | 10 min, zablokowany |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO |  | 0 | 0 | blokada Incapsula |
| WEL | oracle | 3 | 0 | odrzucone strony: 3 |
| WIM | northflank | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 1 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML |  | 0 | 0 | blokada Incapsula |
| WTC |  | 0 | 0 | blokada Incapsula |
| WIG | oracle | 0 | 0 |  |

</details>

<details>
<summary><b>13 lis · 18:55</b> · Bez zmian · plebania · oracle · northflank</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg automatyczny [#150](https://github.com/kilerdevs/PlanWAT/actions/runs/43477538480), od planu do raportu 19 min.

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
| WCY | oracle | 1 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 0 | 0 |  |
| WIM | northflank | 0 | 0 |  |

</details>

<details>
<summary><b>13 lis · 18:52</b> · Część stron odrzucona · plebania · oracle · northflank</summary>

Część stron (WEL) nie przeszła kontroli, więc zostają dla nich poprzednie plany. Przebieg uruchomiony ręcznie [#149](https://github.com/kilerdevs/PlanWAT/actions/runs/43476965918), od planu do raportu 20 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WCY, WEL, WIM, WLO, WML, WTC, WIG (pomoc dla oracle) | 42 | 20 min, odrzucone strony na WEL |
| **oracle** | IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla plebania), WCY (pomoc dla plebania) | 27 | 20 min, zablokowany na WTC, WML |
| **northflank** | WIM (pomoc dla plebania), IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 3 | 20 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 19 | odrzucone strony: 1 |
| WEL | plebania | 160 | 24 | z pomocą oracle, odrzucone strony: 3 z 160 |
| WIM | plebania | 88 | 10 | z pomocą northflank, oracle |
| IOE | oracle | 15 | 0 | z pomocą northflank |
| WCY | plebania | 186 | 0 | z pomocą oracle, blokada dla northflank, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | plebania | 162 | 8 | blokada dla oracle |
| WTC | plebania | 23 | 11 | blokada dla oracle |
| WIG | oracle | 33 | 0 | z pomocą plebania, northflank |

</details>

<details>
<summary><b>13 lis · 10:46</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WCY, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#148](https://github.com/kilerdevs/PlanWAT/actions/runs/43404099643), od planu do raportu 36 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 2 | 34 min, zablokowany na WLO, WCY, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 2 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 48 | 0 | blokada, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 27 | 0 | z pomocą northflank |
| WIM | northflank | 50 | 2 | z pomocą oracle |

</details>

<details>
<summary><b>13 lis · 02:15</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#147](https://github.com/kilerdevs/PlanWAT/actions/runs/43343452080), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 10 | 23 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, IOE (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 10 | 0 | z pomocą northflank |
| WCY | oracle | 186 | 10 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 33 | 0 |  |
| WIM | northflank | 52 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>12 lis · 19:28</b> · Zmiany w 38 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 38 planów. Przebieg automatyczny [#146](https://github.com/kilerdevs/PlanWAT/actions/runs/43280095510), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, IOE (pomoc dla oracle), WIM (pomoc dla northflank), WCY (pomoc dla oracle), WIG (pomoc dla oracle) | 28 | 23 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla plebania), WEL (pomoc dla plebania) | 9 | 20 min |
| **northflank** | WIM, WIG (pomoc dla oracle) | 1 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 140 | 6 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 23 |  |
| WTC | plebania | 23 | 2 |  |
| IOE | oracle | 9 | 0 | z pomocą plebania |
| WCY | oracle | 69 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 21 | 0 | z pomocą northflank, plebania |
| WIM | northflank | 37 | 1 | z pomocą oracle, plebania |

</details>

<details>
<summary><b>12 lis · 10:58</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#145](https://github.com/kilerdevs/PlanWAT/actions/runs/43196162350), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 3 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 5 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 186 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 29 | 0 | z pomocą northflank |
| WIM | northflank | 52 | 5 | z pomocą oracle |

</details>

<details>
<summary><b>12 lis · 01:53</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WTC zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg automatyczny [#144](https://github.com/kilerdevs/PlanWAT/actions/runs/43130531590), od planu do raportu 25 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank) | 0 | 24 min, zablokowany na WLO, WML, WTC |
| **northflank** | WIM, WIG (pomoc dla oracle) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle | 0 | 0 | blokada Incapsula |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 |
| IOE | oracle | 15 | 0 |  |
| WCY | oracle | 135 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 | blokada Incapsula |
| WTC | oracle | 0 | 0 | blokada Incapsula |
| WIG | oracle | 26 | 0 | z pomocą northflank |
| WIM | northflank | 51 | 0 | z pomocą oracle |

</details>

<details>
<summary><b>11 lis · 18:57</b> · Zmiany w 2 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 2 planów. Przebieg automatyczny [#143](https://github.com/kilerdevs/PlanWAT/actions/runs/43073051284), od planu do raportu 24 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WML, WTC, WIM (pomoc dla northflank), WCY (pomoc dla oracle) | 0 | 23 min |
| **oracle** | IOE, WCY, WIG, WIM (pomoc dla northflank), WEL (pomoc dla plebania) | 1 | 20 min |
| **northflank** | WIM, IOE (pomoc dla oracle), WIG (pomoc dla oracle) | 1 | 3 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 | odrzucone strony: 1 |
| WEL | plebania | 147 | 0 | z pomocą oracle, odrzucone strony: 3 |
| WML | plebania | 162 | 0 |  |
| WTC | plebania | 23 | 0 |  |
| IOE | oracle | 10 | 1 | z pomocą northflank |
| WCY | oracle | 94 | 0 | z pomocą plebania, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WIG | oracle | 25 | 0 | z pomocą northflank |
| WIM | northflank | 34 | 0 | z pomocą oracle, plebania |

</details>

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

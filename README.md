# Odświeżanie planów: ostatnie przebiegi

> [!WARNING]
> **Ostatni przebieg: bez zmian.** 14 lis 2026 · 12:57 · **oracle** · **northflank** · ~~plebania~~ · 22 min · [przebieg #158](https://github.com/kilerdevs/PlanWAT/actions/runs/43592467848)
> Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 14 lis · 12:57 | Bez zmian | **oracle** (IOE, WCY, WEL, WIG, WTC przez Tor, WIM (pomoc dla northflank), WML (pomoc dla northflank przez Tor)) · **northflank** (WIM, WLO przez Tor, WML przez Tor, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez Tor), WIG (pomoc dla oracle)) · ~~plebania~~ | 747 | 22 min | [#158](https://github.com/kilerdevs/PlanWAT/actions/runs/43592467848) |
| 14 lis · 07:47 | Zmiany w 13 planach | **oracle** (IOE, WCY, WEL, WIG, WML przez proxy, WTC przez proxy, WIM (pomoc dla northflank)) · **northflank** (WIM, WLO przez proxy, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez proxy), WTC (pomoc dla oracle przez proxy), WML (pomoc dla oracle przez proxy), WIG (pomoc dla oracle)) · ~~plebania~~ | 798 | 22 min | [#157](https://github.com/kilerdevs/PlanWAT/actions/runs/43567992348) |
| 14 lis · 00:43 | Bez zmian | **oracle** (IOE, WCY, WEL, WIG, WIM, WML, WTC przez proxy) · **northflank** (WLO przez proxy, WTC (pomoc dla oracle przez proxy)) · ~~plebania~~ | 40 | 6 min | [#156](https://github.com/kilerdevs/PlanWAT/actions/runs/43529250060) |
| 13 lis · 23:17 | Bez zmian | **oracle** (IOE, WCY, WEL, WIG, WIM (pomoc dla northflank), WML (pomoc dla northflank przez proxy), WTC (pomoc dla northflank przez proxy)) · **northflank** (WIM, WLO przez proxy, WML przez proxy, WTC przez proxy, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez proxy), WIG (pomoc dla oracle)) · ~~plebania~~ | 707 | 19 min | [#155](https://github.com/kilerdevs/PlanWAT/actions/runs/43518082771) |
| 13 lis · 22:22 | Zablokowany | **oracle** · **northflank** · ~~plebania~~ | 0 | 13 min | [#154](https://github.com/kilerdevs/PlanWAT/actions/runs/43510057757) |
| 13 lis · 21:36 | Sprawdzono 5 z 8 wydziałów | **oracle** (IOE, WEL, WIG, WIM, WTC przez proxy) · **northflank** (WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG) · ~~plebania~~ | 43 | 28 min | [#153](https://github.com/kilerdevs/PlanWAT/actions/runs/43503109799) |
| 13 lis · 19:31 | Sprawdzono 5 z 8 wydziałów | **oracle** (IOE, WCY, WEL, WIG) · **northflank** (WIM) · ~~plebania~~ | 4 | 11 min | [#151](https://github.com/kilerdevs/PlanWAT/actions/runs/43483477086) |
| 13 lis · 18:55 | Bez zmian | **plebania** (WLO, WEL, WML, WTC) · **oracle** (IOE, WCY, WIG) · **northflank** (WIM) | 5 | 19 min | [#150](https://github.com/kilerdevs/PlanWAT/actions/runs/43477538480) |
| 13 lis · 18:52 | Zmiany w 72 planach | **plebania** (WCY, WEL, WIM, WLO, WML, WTC, WIG (pomoc dla oracle)) · **oracle** (IOE, WIG, WEL (pomoc dla plebania), WIM (pomoc dla plebania), WCY (pomoc dla plebania)) · **northflank** (WIM (pomoc dla plebania), IOE (pomoc dla oracle), WIG (pomoc dla oracle)) | 798 | 20 min | [#149](https://github.com/kilerdevs/PlanWAT/actions/runs/43476965918) |
| 13 lis · 10:46 | Sprawdzono 4 z 8 wydziałów | **oracle** (WLO, WEL, IOE, WCY, WML, WTC, WIG, WIM (pomoc dla northflank)) · **northflank** (WIM, WIG (pomoc dla oracle)) · ~~plebania~~ | 300 | 36 min | [#148](https://github.com/kilerdevs/PlanWAT/actions/runs/43404099643) |

## Szczegóły

<details>
<summary><b>14 lis · 12:57</b> · Bez zmian · oracle · northflank</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg uruchomiony ręcznie [#158](https://github.com/kilerdevs/PlanWAT/actions/runs/43592467848), od planu do raportu 22 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG, WTC przez Tor, WIM (pomoc dla northflank), WML (pomoc dla northflank przez Tor) | 0 | 21 min, zablokowany na WLO |
| **northflank** | WIM, WLO przez Tor, WML przez Tor, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez Tor), WIG (pomoc dla oracle) | 0 | 21 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank | 131 | 0 | przez Tor na northflank, blokada dla oracle, odrzucone strony: 1 |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 z 160 |
| WIM | northflank | 88 | 0 | z pomocą oracle |
| IOE | oracle | 15 | 0 | z pomocą northflank |
| WCY | oracle | 135 | 0 | z pomocą northflank, przez Tor na northflank, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | northflank | 162 | 0 | z pomocą oracle, przez Tor na northflank, oracle |
| WTC | oracle | 23 | 0 | przez Tor na oracle |
| WIG | oracle | 33 | 0 | z pomocą northflank |

</details>

<details>
<summary><b>14 lis · 07:47</b> · Zmiany w 13 planach · oracle · northflank</summary>

Pobrano nowe wersje 13 planów. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg automatyczny [#157](https://github.com/kilerdevs/PlanWAT/actions/runs/43567992348), od planu do raportu 22 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG, WML przez proxy, WTC przez proxy, WIM (pomoc dla northflank) | 3 | 21 min, zablokowany na WLO |
| **northflank** | WIM, WLO przez proxy, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez proxy), WTC (pomoc dla oracle przez proxy), WML (pomoc dla oracle przez proxy), WIG (pomoc dla oracle) | 10 | 21 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank | 131 | 0 | przez proxy (pula) na northflank, blokada dla oracle, odrzucone strony: 1 |
| WEL | oracle | 160 | 0 | odrzucone strony: 3 z 160 |
| WIM | northflank | 88 | 0 | z pomocą oracle |
| IOE | oracle | 15 | 0 | z pomocą northflank |
| WCY | oracle | 186 | 13 | z pomocą northflank, przez proxy (pula) na northflank, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 162 | 0 | z pomocą northflank, przez proxy (pula) na northflank, oracle |
| WTC | oracle | 23 | 0 | z pomocą northflank, przez proxy (pula) na northflank, oracle |
| WIG | oracle | 33 | 0 | z pomocą northflank |

</details>

<details>
<summary><b>14 lis · 00:43</b> · Bez zmian · oracle · northflank</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg automatyczny [#156](https://github.com/kilerdevs/PlanWAT/actions/runs/43529250060), od planu do raportu 6 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG, WIM, WML, WTC przez proxy | 0 | 5 min, zablokowany na WLO |
| **northflank** | WLO przez proxy, WTC (pomoc dla oracle przez proxy) | 0 | 6 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank | 1 | 0 | przez proxy (pula) na northflank, blokada dla oracle, odrzucone strony: 1 |
| WEL | oracle | 27 | 0 | odrzucone strony: 3 z 27 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | oracle | 1 | 0 | odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle | 0 | 0 |  |
| WTC | oracle | 11 | 0 | z pomocą northflank, przez proxy (pula) na northflank, oracle |
| WIG | oracle | 0 | 0 |  |

</details>

<details>
<summary><b>13 lis · 23:17</b> · Bez zmian · oracle · northflank</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg uruchomiony ręcznie [#155](https://github.com/kilerdevs/PlanWAT/actions/runs/43518082771), od planu do raportu 19 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WCY, WEL, WIG, WIM (pomoc dla northflank), WML (pomoc dla northflank przez proxy), WTC (pomoc dla northflank przez proxy) | 0 | 18 min, zablokowany na WLO |
| **northflank** | WIM, WLO przez proxy, WML przez proxy, WTC przez proxy, IOE (pomoc dla oracle), WCY (pomoc dla oracle przez proxy), WIG (pomoc dla oracle) | 0 | 18 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank | 131 | 0 | przez proxy (pula) na northflank, blokada dla oracle, odrzucone strony: 1 |
| WEL | oracle | 136 | 0 | odrzucone strony: 3 z 136 |
| WIM | northflank | 84 | 0 | z pomocą oracle |
| IOE | oracle | 15 | 0 | z pomocą northflank |
| WCY | oracle | 135 | 0 | z pomocą northflank, przez proxy (pula) na northflank, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | northflank | 162 | 0 | z pomocą oracle, przez proxy (pula) na northflank, oracle |
| WTC | northflank | 11 | 0 | z pomocą oracle, przez proxy (pula) na northflank, oracle |
| WIG | oracle | 33 | 0 | z pomocą northflank |

</details>

<details>
<summary><b>13 lis · 22:22</b> · Zablokowany · oracle · northflank</summary>

Strona wydziału WLO, WML, WCY zablokowała pobieranie. Zostają poprzednie plany, następny przebieg spróbuje znowu. Przebieg uruchomiony ręcznie [#154](https://github.com/kilerdevs/PlanWAT/actions/runs/43510057757), od planu do raportu 13 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** |  | 0 | 7 min, zablokowany na WLO, WML, WCY |
| **northflank** |  | 0 | 12 min, zablokowany |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO |  | 0 | 0 | blokada Incapsula |
| WML |  | 0 | 0 | blokada Incapsula |
| WCY |  | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>13 lis · 21:36</b> · Sprawdzono 5 z 8 wydziałów · oracle · northflank</summary>

Nie wszystko zostało sprawdzone (WLO, WCY, WML). Zostają poprzednie plany, resztę dokończy następny przebieg. Przebieg uruchomiony ręcznie [#153](https://github.com/kilerdevs/PlanWAT/actions/runs/43503109799), od planu do raportu 28 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle** | IOE, WEL, WIG, WIM, WTC przez proxy | 0 | 27 min, zablokowany na WML, WLO, WCY |
| **northflank** | WLO, WEL, WIM, IOE, WCY, WML, WTC, WIG | 0 | brak raportu |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank | – | – | blokada dla oracle, brak danych z tego przebiegu |
| WEL | oracle | 27 | 0 | odrzucone strony: 3 z 27 |
| WIM | oracle | 4 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WCY | northflank | – | – | blokada dla oracle, brak danych z tego przebiegu |
| WML | northflank | – | – | blokada dla oracle, brak danych z tego przebiegu |
| WTC | oracle | 12 | 0 | przez proxy (pula) na oracle |
| WIG | oracle | 0 | 0 |  |

</details>

<details>
<summary><b>13 lis · 19:31</b> · Sprawdzono 5 z 8 wydziałów · oracle · northflank</summary>

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
<summary><b>13 lis · 18:52</b> · Zmiany w 72 planach · plebania · oracle · northflank</summary>

Pobrano nowe wersje 72 planów. Część stron (WEL) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg uruchomiony ręcznie [#149](https://github.com/kilerdevs/PlanWAT/actions/runs/43476965918), od planu do raportu 20 min.

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
<summary><b>13 lis · 10:46</b> · Sprawdzono 4 z 8 wydziałów · oracle · northflank</summary>

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

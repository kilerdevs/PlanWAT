# Odświeżanie planów: ostatnie przebiegi

> [!WARNING]
> **Ostatni przebieg: bez zmian.** 23 lis 2026 · 13:23 · **oracle1** · **oracle2** · **oracle3** · **northflank1** · **northflank2** · ~~plebania~~ · 5 min · [przebieg #192](https://github.com/kilerdevs/PlanWAT/actions/runs/45173772944)
> Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WML) nie przeszła kontroli, więc dla nich zostają poprzednie wersje.

Ostatnie 10 przebiegów workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 23 lis · 13:23 | Bez zmian | **oracle1** (IOE, WIG, WML przez Tor) · **oracle2** (WTC, WIM (pomoc dla oracle3)) · **oracle3** (WCY, WEL, WIM, WLO przez Tor) · **northflank1** · **northflank2** (WIM (pomoc dla oracle3)) · ~~plebania~~ | 51 | 5 min | [#192](https://github.com/kilerdevs/PlanWAT/actions/runs/45173772944) |
| 23 lis · 11:23 | Zmiany w 22 planach | **oracle1** (IOE, WIG, WTC przez Tor, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez proxy)) · **oracle2** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WIG (pomoc dla oracle1)) · **oracle3** (WML przez Tor, WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WIG (pomoc dla oracle1)) · **northflank1** (WIM (pomoc dla oracle2), WCY (pomoc dla oracle2 przez Tor), IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy)) · **northflank2** (WLO przez proxy, WIM (pomoc dla oracle2), IOE (pomoc dla oracle1), WCY (pomoc dla oracle2 przez Tor), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy)) · ~~plebania~~ | 821 | 11 min | [#191](https://github.com/kilerdevs/PlanWAT/actions/runs/45155586562) |
| 23 lis · 03:55 | Zmiana w 1 planie | **oracle1** (IOE, WIG, WTC przez Tor, WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), WEL (pomoc dla oracle3), WML (pomoc dla oracle2 przez proxy), WLO (pomoc dla northflank2 przez proxy)) · **oracle2** (WML przez proxy, WEL (pomoc dla oracle3), WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **oracle3** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle2 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **northflank1** · **northflank2** (WLO przez Tor) · ~~plebania~~ | 798 | 11 min | [#190](https://github.com/kilerdevs/PlanWAT/actions/runs/45102886063) |
| 22 lis · 21:46 | Bez zmian | **oracle1** (IOE, WIG, WTC przez Tor, WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WML (pomoc dla oracle3 przez Tor)) · **oracle2** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank1 przez Tor)) · **oracle3** (WML przez Tor, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank1 przez Tor)) · **northflank1** (WLO przez Tor, WML (pomoc dla oracle3 przez proxy)) · **northflank2** (WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank1 przez Tor)) · ~~plebania~~ | 747 | 10 min | [#189](https://github.com/kilerdevs/PlanWAT/actions/runs/45068303449) |
| 22 lis · 13:43 | Zmiany w 2 planach | **oracle1** (IOE, WIG, WTC przez Tor, WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez Tor)) · **oracle2** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez Tor)) · **oracle3** (WML przez Tor, WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor)) · **northflank1** · **northflank2** (WLO przez Tor) · ~~plebania~~ | 798 | 23 min | [#188](https://github.com/kilerdevs/PlanWAT/actions/runs/45023746956) |
| 22 lis · 03:23 | Zmiany w 6 planach | **oracle1** (IOE, WIG, WTC przez proxy, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy)) · **oracle2** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WTC (pomoc dla oracle1 przez proxy), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **oracle3** (WML przez proxy, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WTC (pomoc dla oracle1 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **northflank1** · **northflank2** (WLO przez proxy, WCY (pomoc dla oracle2 przez proxy), WML (pomoc dla oracle3 przez proxy)) · ~~plebania~~ | 747 | 13 min | [#187](https://github.com/kilerdevs/PlanWAT/actions/runs/44975871739) |
| 21 lis · 21:36 | Bez zmian | **oracle1** (IOE, WIG, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WTC (pomoc dla oracle2 przez Tor), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy)) · **oracle2** (WCY, WEL, WIM, WTC przez Tor, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **oracle3** (WML przez Tor, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor)) · **northflank1** (WCY (pomoc dla oracle2 przez Tor), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy)) · **northflank2** (WLO przez proxy, WML (pomoc dla oracle3 przez proxy)) · ~~plebania~~ | 798 | 10 min | [#186](https://github.com/kilerdevs/PlanWAT/actions/runs/44947179538) |
| 21 lis · 13:51 | Zmiana w 1 planie | **oracle1** (IOE, WIG, WML przez Tor, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WLO (pomoc dla northflank2 przez proxy)) · **oracle2** (WCY, WEL, WIM, WTC przez Tor, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle1 przez Tor), WLO (pomoc dla northflank2 przez proxy)) · **oracle3** (WIM (pomoc dla oracle2), WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), IOE (pomoc dla oracle1), WML (pomoc dla oracle1 przez Tor), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor)) · **northflank1** · **northflank2** (WLO przez proxy) · ~~plebania~~ | 747 | 13 min | [#185](https://github.com/kilerdevs/PlanWAT/actions/runs/44905922167) |
| 21 lis · 04:18 | Zmiany w 6 planach | **oracle1** (IOE, WIG, WLO przez Tor, WTC przez Tor, WCY (pomoc dla oracle3), WIM (pomoc dla oracle3), WEL (pomoc dla oracle3), WML (pomoc dla oracle2 przez proxy)) · **oracle2** (WML przez Tor, WIM (pomoc dla oracle3), WEL (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla oracle1 przez proxy)) · **oracle3** (WCY, WEL, WIM, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle2 przez Tor), WLO (pomoc dla oracle1 przez proxy)) · **northflank1** (WLO (pomoc dla oracle1 przez proxy)) · **northflank2** · ~~plebania~~ | 798 | 12 min | [#184](https://github.com/kilerdevs/PlanWAT/actions/runs/44860418922) |
| 20 lis · 22:53 | Zmiany w 29 planach | **oracle1** (IOE, WIG, WEL (pomoc dla oracle3), WCY (pomoc dla oracle3), WIM (pomoc dla oracle3), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez proxy)) · **oracle2** (WEL (pomoc dla oracle3), WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez proxy)) · **oracle3** (WCY, WEL, WIM, WML przez Tor, WTC przez Tor, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy)) · **northflank1** · **northflank2** (WLO przez proxy, WML (pomoc dla oracle3 przez proxy)) · ~~plebania~~ | 747 | 13 min | [#183](https://github.com/kilerdevs/PlanWAT/actions/runs/44824214056) |

## Szczegóły

<details>
<summary><b>23 lis · 13:23</b> · Bez zmian · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Część stron (WML) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg uruchomiony ręcznie [#192](https://github.com/kilerdevs/PlanWAT/actions/runs/45173772944), od planu do raportu 5 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WML przez Tor | 0 | 3 min, zablokowany na WLO, WTC |
| **oracle2** | WTC, WIM (pomoc dla oracle3) | 0 | 4 min, zablokowany na WLO, WML |
| **oracle3** | WCY, WEL, WIM, WLO przez Tor | 0 | 4 min, zablokowany na WTC, WML |
| **northflank1** |  | 0 | 4 min |
| **northflank2** | WIM (pomoc dla oracle3) | 0 | 4 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle3 | 3 | 0 | przez Tor na oracle3, blokada dla oracle1, oracle2 |
| WEL | oracle3 | 3 | 0 | odrzucone strony: 3 |
| WIM | oracle3 | 9 | 0 | z pomocą northflank2, oracle2 |
| IOE | oracle1 | 0 | 0 |  |
| WCY | oracle3 | 1 | 0 | bez planu na ten semestr: 51 |
| WML | oracle1 | 27 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3, odrzucone strony: 18 z 27 |
| WTC | oracle2 | 0 | 0 | blokada dla oracle1, oracle3 |
| WIG | oracle1 | 8 | 0 |  |

</details>

<details>
<summary><b>23 lis · 11:23</b> · Zmiany w 22 planach · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nowe wersje 22 planów. Część stron (WML) nie przeszła kontroli, więc dla nich zostają poprzednie wersje. Przebieg uruchomiony ręcznie [#191](https://github.com/kilerdevs/PlanWAT/actions/runs/45155586562), od planu do raportu 11 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WTC przez Tor, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez proxy) | 1 | 10 min, zablokowany na WLO |
| **oracle2** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WIG (pomoc dla oracle1) | 7 | 10 min, zablokowany na WTC, WLO |
| **oracle3** | WML przez Tor, WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WIG (pomoc dla oracle1) | 1 | 10 min, zablokowany na WLO, WTC |
| **northflank1** | WIM (pomoc dla oracle2), WCY (pomoc dla oracle2 przez Tor), IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy) | 6 | 10 min |
| **northflank2** | WLO przez proxy, WIM (pomoc dla oracle2), IOE (pomoc dla oracle1), WCY (pomoc dla oracle2 przez Tor), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy) | 7 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 132 | 3 | z pomocą northflank1, przez proxy (pula) na northflank1, northflank2, blokada dla oracle1, oracle2, oracle3 |
| WEL | oracle2 | 214 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 89 | 9 | z pomocą oracle3, northflank1, oracle1, northflank2 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle2, northflank2, northflank1 |
| WCY | oracle2 | 135 | 1 | z pomocą northflank2, oracle1, oracle3, northflank1, przez Tor na northflank1, northflank2, bez planu na ten semestr: 51 |
| WML | oracle3 | 180 | 9 | z pomocą oracle1, northflank1, oracle2, northflank2, przez proxy (pula) na northflank1, northflank2, oracle1, przez Tor na oracle2, oracle3, odrzucone strony: 18 z 180 |
| WTC | oracle1 | 23 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle2, oracle3, northflank2 |

</details>

<details>
<summary><b>23 lis · 03:55</b> · Zmiana w 1 planie · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nową wersję 1 planu. Przebieg automatyczny [#190](https://github.com/kilerdevs/PlanWAT/actions/runs/45102886063), od planu do raportu 11 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WTC przez Tor, WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), WEL (pomoc dla oracle3), WML (pomoc dla oracle2 przez proxy), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min |
| **oracle2** | WML przez proxy, WEL (pomoc dla oracle3), WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min, zablokowany na WTC |
| **oracle3** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle2 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 1 | 10 min, zablokowany na WTC |
| **northflank1** |  | 0 | 10 min |
| **northflank2** | WLO przez Tor | 0 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 0 | z pomocą oracle1, oracle2, oracle3, przez proxy (pula) na oracle1, oracle2, oracle3, przez Tor na northflank2, odrzucone strony: 3 |
| WEL | oracle3 | 160 | 0 | z pomocą oracle2, oracle1, odrzucone strony: 3 |
| WIM | oracle3 | 88 | 0 | z pomocą oracle2, oracle1 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle2, oracle3 |
| WCY | oracle3 | 186 | 1 | z pomocą oracle1, oracle2, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle2 | 162 | 0 | z pomocą oracle3, oracle1, przez proxy (pula) na oracle1, oracle2, oracle3 |
| WTC | oracle1 | 23 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>22 lis · 21:46</b> · Bez zmian · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg automatyczny [#189](https://github.com/kilerdevs/PlanWAT/actions/runs/45068303449), od planu do raportu 10 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WTC przez Tor, WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WML (pomoc dla oracle3 przez Tor) | 0 | 9 min |
| **oracle2** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank1 przez Tor) | 0 | 9 min, zablokowany na WTC |
| **oracle3** | WML przez Tor, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank1 przez Tor) | 0 | 9 min, zablokowany na WTC |
| **northflank1** | WLO przez Tor, WML (pomoc dla oracle3 przez proxy) | 0 | 9 min |
| **northflank2** | WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank1 przez Tor) | 0 | 9 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank1 | 131 | 0 | z pomocą oracle2, northflank2, oracle3, przez Tor na northflank1, northflank2, oracle2, oracle3, odrzucone strony: 3 |
| WEL | oracle2 | 160 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 88 | 0 | z pomocą oracle3, oracle1 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle2, oracle3 |
| WCY | oracle2 | 135 | 0 | z pomocą oracle3, oracle1, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle3 | 162 | 0 | z pomocą oracle1, northflank2, northflank1, oracle2, przez proxy (pula) na northflank1, northflank2, oracle2, przez Tor na oracle1, oracle3 |
| WTC | oracle1 | 23 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>22 lis · 13:43</b> · Zmiany w 2 planach · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nowe wersje 2 planów. Przebieg automatyczny [#188](https://github.com/kilerdevs/PlanWAT/actions/runs/45023746956), od planu do raportu 23 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WTC przez Tor, WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez Tor) | 0 | 10 min |
| **oracle2** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez Tor) | 1 | 10 min, zablokowany na WTC |
| **oracle3** | WML przez Tor, WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor) | 1 | 10 min, zablokowany na WTC |
| **northflank1** |  | 0 | 22 min |
| **northflank2** | WLO przez Tor | 0 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 0 | z pomocą oracle2, oracle3, oracle1, przez Tor na northflank2, oracle1, oracle2, oracle3, odrzucone strony: 3 |
| WEL | oracle2 | 160 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 88 | 2 | z pomocą oracle3, oracle1 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle2, oracle3 |
| WCY | oracle2 | 186 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle3 | 162 | 0 | z pomocą oracle2, oracle1, przez Tor na oracle1, oracle2, oracle3 |
| WTC | oracle1 | 23 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle2, oracle3 |

</details>

<details>
<summary><b>22 lis · 03:23</b> · Zmiany w 6 planach · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nowe wersje 6 planów. Przebieg automatyczny [#187](https://github.com/kilerdevs/PlanWAT/actions/runs/44975871739), od planu do raportu 13 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WTC przez proxy, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy) | 2 | 9 min |
| **oracle2** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WTC (pomoc dla oracle1 przez proxy), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 2 | 9 min |
| **oracle3** | WML przez proxy, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WTC (pomoc dla oracle1 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 2 | 9 min |
| **northflank1** |  | 0 | 12 min |
| **northflank2** | WLO przez proxy, WCY (pomoc dla oracle2 przez proxy), WML (pomoc dla oracle3 przez proxy) | 0 | 9 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 0 | z pomocą oracle3, oracle2, oracle1, przez proxy (pula) na northflank2, oracle1, oracle2, oracle3, odrzucone strony: 3 |
| WEL | oracle2 | 160 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 88 | 0 | z pomocą oracle3, oracle1 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle2, oracle3 |
| WCY | oracle2 | 135 | 6 | z pomocą northflank2, oracle1, oracle3, przez proxy (pula) na northflank2, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle3 | 162 | 0 | z pomocą oracle2, northflank2, oracle1, przez proxy (pula) na northflank2, oracle1, oracle2, oracle3 |
| WTC | oracle1 | 23 | 0 | z pomocą oracle3, oracle2, przez proxy (pula) na oracle1, oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>21 lis · 21:36</b> · Bez zmian · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Sprawdzono wszystkie wydziały, żaden plan się nie zmienił. Przebieg automatyczny [#186](https://github.com/kilerdevs/PlanWAT/actions/runs/44947179538), od planu do raportu 10 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WTC (pomoc dla oracle2 przez Tor), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min |
| **oracle2** | WCY, WEL, WIM, WTC przez Tor, IOE (pomoc dla oracle1), WML (pomoc dla oracle3 przez proxy), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 0 | 9 min |
| **oracle3** | WML przez Tor, WIM (pomoc dla oracle2), WEL (pomoc dla oracle2), WCY (pomoc dla oracle2), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor) | 0 | 10 min, zablokowany na WTC |
| **northflank1** | WCY (pomoc dla oracle2 przez Tor), WML (pomoc dla oracle3 przez proxy), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min |
| **northflank2** | WLO przez proxy, WML (pomoc dla oracle3 przez proxy) | 0 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 0 | z pomocą oracle1, northflank1, oracle2, oracle3, przez proxy (pula) na northflank1, northflank2, oracle1, oracle2, przez Tor na oracle3, odrzucone strony: 3 |
| WEL | oracle2 | 160 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 88 | 0 | z pomocą oracle3 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle3, oracle2 |
| WCY | oracle2 | 186 | 0 | z pomocą oracle1, oracle3, northflank1, przez Tor na northflank1, blokada dla northflank2, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle3 | 162 | 0 | z pomocą northflank1, oracle2, oracle1, northflank2, przez proxy (pula) na northflank1, northflank2, oracle1, oracle2, przez Tor na oracle3 |
| WTC | oracle2 | 23 | 0 | z pomocą oracle1, przez Tor na oracle1, oracle2, blokada dla oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>21 lis · 13:51</b> · Zmiana w 1 planie · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nową wersję 1 planu. Przebieg automatyczny [#185](https://github.com/kilerdevs/PlanWAT/actions/runs/44905922167), od planu do raportu 13 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WML przez Tor, WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), WIM (pomoc dla oracle2), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min, zablokowany na WTC |
| **oracle2** | WCY, WEL, WIM, WTC przez Tor, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle1 przez Tor), WLO (pomoc dla northflank2 przez proxy) | 0 | 10 min |
| **oracle3** | WIM (pomoc dla oracle2), WCY (pomoc dla oracle2), WEL (pomoc dla oracle2), IOE (pomoc dla oracle1), WML (pomoc dla oracle1 przez Tor), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez Tor) | 1 | 10 min, zablokowany na WTC |
| **northflank1** |  | 0 | 12 min |
| **northflank2** | WLO przez proxy | 0 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 0 | z pomocą oracle3, oracle2, oracle1, przez proxy (pula) na northflank2, oracle1, oracle2, przez Tor na oracle3, odrzucone strony: 3 |
| WEL | oracle2 | 160 | 0 | z pomocą oracle1, oracle3, odrzucone strony: 3 |
| WIM | oracle2 | 88 | 0 | z pomocą oracle3, oracle1 |
| IOE | oracle1 | 15 | 1 | z pomocą oracle2, oracle3 |
| WCY | oracle2 | 135 | 0 | z pomocą oracle3, oracle1, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle1 | 162 | 0 | z pomocą oracle3, oracle2, przez Tor na oracle1, oracle2, oracle3 |
| WTC | oracle2 | 23 | 0 | przez Tor na oracle2, blokada dla oracle1, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>21 lis · 04:18</b> · Zmiany w 6 planach · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nowe wersje 6 planów. Przebieg automatyczny [#184](https://github.com/kilerdevs/PlanWAT/actions/runs/44860418922), od planu do raportu 12 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WLO przez Tor, WTC przez Tor, WCY (pomoc dla oracle3), WIM (pomoc dla oracle3), WEL (pomoc dla oracle3), WML (pomoc dla oracle2 przez proxy) | 2 | 11 min |
| **oracle2** | WML przez Tor, WIM (pomoc dla oracle3), WEL (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla oracle1 przez proxy) | 2 | 11 min, zablokowany na WTC |
| **oracle3** | WCY, WEL, WIM, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle2 przez Tor), WLO (pomoc dla oracle1 przez proxy) | 2 | 11 min, zablokowany na WTC |
| **northflank1** | WLO (pomoc dla oracle1 przez proxy) | 0 | 11 min |
| **northflank2** |  | 0 | 11 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | oracle1 | 131 | 0 | z pomocą northflank1, oracle2, oracle3, przez proxy (pula) na northflank1, oracle2, oracle3, przez Tor na oracle1, bez listy grup na northflank2, odrzucone strony: 3 |
| WEL | oracle3 | 160 | 0 | z pomocą oracle2, oracle1, odrzucone strony: 3 |
| WIM | oracle3 | 88 | 0 | z pomocą oracle1, oracle2 |
| IOE | oracle1 | 15 | 0 | z pomocą oracle3, oracle2 |
| WCY | oracle3 | 186 | 6 | z pomocą oracle1, oracle2, bez listy grup na northflank2, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle2 | 162 | 0 | z pomocą oracle1, oracle3, przez proxy (pula) na oracle1, przez Tor na oracle2, oracle3, bez listy grup na northflank2 |
| WTC | oracle1 | 23 | 0 | przez Tor na oracle1, blokada dla oracle2, oracle3 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle3, oracle2 |

</details>

<details>
<summary><b>20 lis · 22:53</b> · Zmiany w 29 planach · oracle1 · oracle2 · oracle3 · northflank1 · northflank2</summary>

Pobrano nowe wersje 29 planów. Przebieg automatyczny [#183](https://github.com/kilerdevs/PlanWAT/actions/runs/44824214056), od planu do raportu 13 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **oracle1** | IOE, WIG, WEL (pomoc dla oracle3), WCY (pomoc dla oracle3), WIM (pomoc dla oracle3), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez proxy) | 5 | 9 min, zablokowany na WTC |
| **oracle2** | WEL (pomoc dla oracle3), WIM (pomoc dla oracle3), WCY (pomoc dla oracle3), IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WML (pomoc dla oracle3 przez Tor), WLO (pomoc dla northflank2 przez proxy) | 2 | 9 min, zablokowany na WTC |
| **oracle3** | WCY, WEL, WIM, WML przez Tor, WTC przez Tor, IOE (pomoc dla oracle1), WIG (pomoc dla oracle1), WLO (pomoc dla northflank2 przez proxy) | 12 | 10 min |
| **northflank1** |  | 0 | 12 min |
| **northflank2** | WLO przez proxy, WML (pomoc dla oracle3 przez proxy) | 10 | 10 min |
| plebania | | | wyłączony |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | northflank2 | 131 | 15 | z pomocą oracle3, oracle1, oracle2, przez proxy (pula) na northflank2, oracle1, oracle2, oracle3, odrzucone strony: 3 |
| WEL | oracle3 | 160 | 4 | z pomocą oracle1, oracle2, odrzucone strony: 3 |
| WIM | oracle3 | 88 | 0 | z pomocą oracle2, oracle1 |
| IOE | oracle1 | 15 | 1 | z pomocą oracle3, oracle2 |
| WCY | oracle3 | 135 | 0 | z pomocą oracle2, oracle1, odrzucone strony: 1, bez planu na ten semestr: 51 |
| WML | oracle3 | 162 | 0 | z pomocą northflank2, oracle1, oracle2, przez proxy (pula) na northflank2, przez Tor na oracle1, oracle2, oracle3 |
| WTC | oracle3 | 23 | 9 | przez Tor na oracle3, blokada dla oracle1, oracle2 |
| WIG | oracle1 | 33 | 0 | z pomocą oracle2, oracle3 |

</details>

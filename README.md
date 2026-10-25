# Odświeżanie planów: ostatnie przebiegi

> [!TIP]
> **Ostatni przebieg: bez zmian.** 25 paź 2026 · 22:56 · **plebania** · **oracle** · 14 min · [przebieg #62](https://github.com/kilerdevs/PlanWAT/actions/runs/40237831558)

Ostatnie 3 przebiegi workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, opis w [docs/REFRESH.md](https://github.com/kilerdevs/PlanWAT/blob/master/docs/REFRESH.md)). Ta sama lista jest na stronie: [https://kilerdevs.github.io/PlanWAT/stan/](https://kilerdevs.github.io/PlanWAT/stan/).

| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |
|---|---|---|--:|--:|---|
| 25 paź · 22:56 | Bez zmian | **plebania** (WLO, WEL, WCY, WML, WTC (od oracle)) · **oracle** (WIM, IOE, WTC) | 68 | 14 min | [#62](https://github.com/kilerdevs/PlanWAT/actions/runs/40237831558) |
| 25 paź · 21:59 | Zablokowany | **plebania** (WLO, WEL, WCY, WML) · **oracle** (WIM, IOE, WTC) | 101 | 50 min | [#61](https://github.com/kilerdevs/PlanWAT/actions/runs/40233347824) |
| 25 paź · 21:46 | Zablokowany | **plebania** (WLO, WEL, WCY, WML) · **oracle** (WIM, IOE, WTC) | 654 | 37 min | [#60](https://github.com/kilerdevs/PlanWAT/actions/runs/40232365038) |

## Szczegóły

<details>
<summary><b>25 paź · 22:56</b> · Bez zmian · plebania · oracle</summary>

Przebieg ręczny [#62](https://github.com/kilerdevs/PlanWAT/actions/runs/40237831558), od planu do raportu 14 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 9 min |
| **oracle** | WIM, IOE, WTC | 0 | 6 min, zablokowany na WTC |
| **plebania** (przejęcie) | WTC (od oracle) | 0 | 4 min |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | pominięte: 3 |
| WCY | plebania | 39 | 0 | bez planu na ten semestr: 38, pominięte: 1 |
| WML | plebania | 3 | 0 | pominięte: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | plebania | 23 | 0 | przejęty po blokadzie na oracle, pominięte: 1 |

</details>

<details>
<summary><b>25 paź · 21:59</b> · Zablokowany · plebania · oracle</summary>

Przebieg zaplanowany [#61](https://github.com/kilerdevs/PlanWAT/actions/runs/40233347824), od planu do raportu 50 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 14 min |
| **oracle** | WIM, IOE, WTC | 0 | 31 min, zablokowany |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 0 | 0 |  |
| WEL | plebania | 3 | 0 | pominięte: 3 |
| WCY | plebania | 95 | 0 | bez planu na ten semestr: 38, pominięte: 1 |
| WML | plebania | 3 | 0 | pominięte: 3 |
| WIM | oracle | 0 | 0 |  |
| IOE | oracle | 0 | 0 |  |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

<details>
<summary><b>25 paź · 21:46</b> · Zablokowany · plebania · oracle</summary>

Przebieg ręczny [#60](https://github.com/kilerdevs/PlanWAT/actions/runs/40232365038), od planu do raportu 37 min.

| Serwer | Wydziały | Zmienione | Stan |
|---|---|--:|---|
| **plebania** | WLO, WEL, WCY, WML | 0 | 36 min |
| **oracle** | WIM, IOE, WTC | 0 | 31 min, zablokowany |

| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |
|---|---|--:|--:|---|
| WLO | plebania | 131 | 0 |  |
| WEL | plebania | 158 | 0 | pominięte: 3 |
| WCY | plebania | 100 | 0 | bez planu na ten semestr: 38, pominięte: 1 |
| WML | plebania | 162 | 0 | pominięte: 3 |
| WIM | oracle | 88 | 0 |  |
| IOE | oracle | 15 | 0 |  |
| WTC | oracle | 0 | 0 | blokada Incapsula |

</details>

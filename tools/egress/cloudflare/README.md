# Relay Cloudflare dla ścian WAT

Ten Worker pobiera strony wydziałów z adresów Cloudflare, które Incapsula wpuszcza, i oddaje runnerowi odpowiedź
upstreamu (status, nagłówki i treść). Uzupełnia pulę proxy z [`tools/egress`](../), a nie ją zastępuje: pula nadal
obsługuje WCY i wszystkie hosty, które sama przepuszcza. Runner korzysta z Workera tylko wtedy, gdy ustawi
`PLANWAT_RELAY_URL` (zob. [`docs/EGRESS.md`](../../../docs/EGRESS.md)).

## Co Worker robi i czego nie robi

- Przyjmuje tylko `GET` i `HEAD` z `Authorization: Bearer $PLANWAT_RELAY_TOKEN`.
- Pobiera wyłącznie `https://` z dokładnie wymienionych hostów (`PLANWAT_RELAY_HOSTS`); nie jest otwartym proxy.
- Sam prowadzi przekierowania (najwyżej 3), ale każdy krok musi zostać na liście hostów.
- Nie przekazuje dalej ciasteczek ani nagłówka `Authorization` wywołującego; nie oddaje też `Set-Cookie`
  ani `Content-Encoding`/`Content-Length` upstreamu. Ciasteczka ustawione przez upstream odtwarza w ramach łańcucha
  przekierowań jednego żądania i trzyma per host w Cache API przez 10 minut — Incapsula odpowiada na pierwsze wejście
  `307` na ten sam URL i oczekuje swoich ciasteczek w powtórce, a bez nich każde żądanie wygląda jak nowy gość.
- Oddaje `ETag` i `Last-Modified`, więc odświeżanie warunkowe (`304`) działa przez relay tak samo jak bezpośrednio.
- WCY celowo nie ma na liście: ten host odpowiada Workerowi `403`, więc zostaje na rotującej puli proxy.

## Wdrożenie

Potrzebne jest darmowe konto Cloudflare i Node.js (do `npx`).

```sh
cd tools/egress/cloudflare
npx wrangler@4 login
npx wrangler@4 deploy
npx wrangler@4 secret put PLANWAT_RELAY_TOKEN   # wklej token, np. z: openssl rand -hex 32
```

`deploy` wypisze adres w rodzaju `https://planwat-egress.<konto>.workers.dev`. Zapisz go jako `PLANWAT_RELAY_URL`.
Sekret musi być ten sam na Workerze i na runnerze; nie wpisuj go do `wrangler.toml` ani do repozytorium.

Listę hostów zmieniasz w `[vars] PLANWAT_RELAY_HOSTS` w `wrangler.toml` i wdrażasz ponownie. Wartość `off` zamyka
relay bez usuwania Workera. Wartość pusta oznacza listę domyślną z `worker.js`.

### Sprawdzenie

```sh
export RELAY=https://planwat-egress.<konto>.workers.dev
export TOKEN=...   # ten sam, który ustawiłeś przez `wrangler secret put`

# 200 i prawdziwy XML indeksu:
curl -fsS -H "Authorization: Bearer $TOKEN" \
  --get --data-urlencode 'url=https://wtc.wat.edu.pl/Plany/index.xml' "$RELAY" | head -c 200

# bez tokenu: 401, a nie zawartość wydziału:
curl -sS -o /dev/null -w '%{http_code}\n' \
  --get --data-urlencode 'url=https://wtc.wat.edu.pl/Plany/index.xml' "$RELAY"

# host spoza listy: 403:
curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  --get --data-urlencode 'url=https://example.com/' "$RELAY"
```

### Runner oracle / plebania

W `.env` runnera (albo w zmiennych usługi):

```sh
PLANWAT_RELAY_URL=https://planwat-egress.<konto>.workers.dev
PLANWAT_RELAY_TOKEN=...
# opcjonalnie: PLANWAT_RELAY_HOSTS=... (domyślnie lista hostów z relay.py; "off" wyłącza relay)
```

Egress runnera musi przepuścić **dokładnie ten hostname** Workera bezpośrednio, poza pulą:

```sh
EGRESS_DIRECT_HOSTS=planwat-egress.<konto>.workers.dev
```

Bez tego egress odpowie `403` (domyślna odmowa), zanim żądanie dotrze do Workera. Nie wpisuj tam całego
`workers.dev`, chyba że świadomie chcesz wpuścić wszystkie Workery Cloudflare.

### Northflank

Northflank nie ma egressu, więc ustawia tylko `PLANWAT_RELAY_URL` i `PLANWAT_RELAY_TOKEN` (oraz opcjonalnie
`PLANWAT_RELAY_HOSTS`). Dzięki temu może brać WLO, WEL, WML, WTC i WIG; WCY nadal wymaga puli, której Northflank
nie ma. Po włączeniu relaya można dopisać te wydziały do `faculties` w `tools/refresh/fleet.json` — bez relaya
zostaw listę taką, jaka jest, bo ściany odrzucą jego adres.

## Limity darmowego planu

- 100 000 żądań dziennie i 10 ms CPU na żądanie (stan na 2026-10-27). Relay zużywa jedno żądanie na stronę;
  przekierowanie to dodatkowe podżądanie, ale nadal jedno żądanie Workera.
- Pełny przebieg wszystkich wydziałów to rząd kilkuset–tysiąca stron, a przebiegi są co 2 h; przy dwóch runnerach
  dzienny ruch pozostaje poniżej limitu. Gdyby limit został osiągnięty, Worker zacznie odpowiadać błędami, a crawler
  potraktuje to jak chwilową awarię i ponowi próbę w następnym przebiegu.
- Cloudflare może zmienić limity; sprawdź aktualny cennik przed wdrożeniem.

## Bezpieczeństwo i utrzymanie

- Token jest jedynym zabezpieczeniem przed wykorzystaniem Workera jako proxy do stron wydziałów. Wyciekły token
  unieważnisz, ustawiając nowy sekret (`wrangler secret put PLANWAT_RELAY_TOKEN`) i aktualizując runner.
- Worker widzi adresy pobieranych stron, a Cloudflare widzi ruch. Nie wysyłaj przez niego danych prywatnych;
  crawling stron wydziałów jest publiczny.
- Worker nie omija `EGRESS_FAIL_CLOSED` dla WCY: ten host nie jest na liście i nie jest pobierany przez Cloudflare.
- Usunięcie Workera: `npx wrangler@4 delete planwat-egress` (najpierw wyłącz relay na runnerach).
- Do testów lokalnych użyj `npx wrangler@4 dev` i pliku `.dev.vars` z `PLANWAT_RELAY_TOKEN=...`; plik jest
  ignorowany przez git.

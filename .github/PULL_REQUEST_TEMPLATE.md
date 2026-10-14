<!--
Dziękujemy za wkład! Wypełnij to, co dotyczy, a resztę usuń. Otwórz PR do gałęzi `dev`.
Podatność bezpieczeństwa? NIE opisuj jej tutaj, użyj prywatnego zgłaszania:
https://github.com/kilerdevs/PlanWAT/security/advisories/new
-->

## Podsumowanie

<!-- Co zmienia ta zmiana, w jednym lub dwóch zdaniach? -->

## Dlaczego

<!-- Problem lub motywacja. Podlinkuj zgłoszenie: Closes #123 -->

## Rodzaj zmiany

- [ ] Plan (nowa grupa, nowy semestr lub poprawka)
- [ ] Poprawka błędu
- [ ] Nowa funkcja
- [ ] Dostępność lub wygląd
- [ ] Refaktoryzacja / porządki (bez zmiany zachowania)
- [ ] Tylko dokumentacja
- [ ] Testy / CI / narzędzia

## Jak to przetestowano?

- [ ] `npm test` przechodzi (czytnik i budowa, potem testy przeglądarkowe)
- [ ] Dodano lub zaktualizowano test, który bez tej zmiany nie przechodzi
- [ ] Obejrzano wynik na telefonie i z włączonym ograniczeniem ruchu (zmiany interfejsu)

## Lista kontrolna: plany

- [ ] Plik to `timetables/<semestr>/<GRUPA>.ics`, UTF-8 z zakończeniami linii CRLF
- [ ] `X-PLAN-GROUP` zgadza się z nazwą pliku, ustawiono początek i koniec semestru
- [ ] Poprawiane zdarzenia zachowały swój `UID`
- [ ] Brak danych kadry: nazwisk, tytułów, kontaktów
- [ ] Nie dotyczy

## Lista kontrolna: bezpieczeństwo i wygląd

- [ ] Brak atrybutów `style="…"` i obsługi `on…=`. Skrypt i styl zostają w haszowanych blokach
- [ ] Dane z kalendarza renderowane przez `textContent`, nigdy `innerHTML`
- [ ] Brak nowej zależności w runtime, skryptu firm trzecich lub zewnętrznego źródła
- [ ] Zgodne z DESIGN.md (tokeny, jeden akcent, cele dotyku 44 px, ruch przez transform/opacity)
- [ ] Nie dotyczy

## Dokumentacja

- [ ] Wpis w `CHANGELOG.md` w sekcji **Unreleased**
- [ ] README / dokumentacja zaktualizowane, jeśli zmieniło się zachowanie lub format kalendarza

## Zrzuty ekranu

<!-- Zmiany interfejsu: przed / po, telefon i pulpit. -->

# arturbyrski.pl

Strona firmy Artur Byrski Link Technologies i polityki prywatności gier. Hostowana na GitHub Pages
(gałąź `main`, domena z pliku `CNAME`).

## Jak to działa

Każda gra ma jeden plik z danymi: `dane/gry/<id-gry>.json` (nazwa, opisy PL/EN, zrzuty ekranu,
lista wydań z notatkami „co nowego”). Skrypt `narzedzia/strona.py` (sam Python, bez bibliotek)
generuje z nich:

| Plik | Dla kogo |
| --- | --- |
| `gry/<id-gry>/index.html` | strona gry: wersja, zrzuty, „Co nowego”, link do Google Play (po premierze) |
| `index.html` | karty gier między `<!-- gry:start -->` a `<!-- gry:koniec -->` (reszta pliku edytowana ręcznie) |
| `api/gry.json` | wszystkie gry, najnowsze wersje, opisy i adresy zrzutów |
| `api/wydania.json` | [JSON Feed 1.1](https://jsonfeed.org/version/1.1) z wydaniami, od najnowszego |
| `feed.xml` | to samo jako RSS |

Plików wygenerowanych nie edytuj ręcznie. Zmień dane i uruchom `python3 narzedzia/strona.py zbuduj`
(albo tylko wypchnij zmianę danych: workflow „Zbuduj stronę” przebuduje stronę sam).

## Automatyczna aktualizacja po wydaniu gry

Workflow wydania w repozytorium gry (np. `psyabx/playgame`, plik `.github/workflows/release.yml`)
po udanej wysyłce do Google Play pobiera to repozytorium, uruchamia

```bash
python3 narzedzia/strona.py wydanie --gra pizamersi --wersja 0.2.0 --kod 105 --sciezka internal \
  --notatki-pl sklep/co-nowego/pl.txt --notatki-en sklep/co-nowego/en.txt --zrzuty sklep/zrzuty
```

i wypycha zmiany na `main`. Ponowne uruchomienie tego samego wydania (ten sam `--kod`) nadpisuje
wpis zamiast go dublować. Link do Google Play pojawia się na stronie dopiero przy pierwszym
wydaniu na ścieżce `production`.

Do wypychania potrzebny jest sekret `STRONA_TOKEN` w repozytorium gry: token fine-grained
z dostępem tylko do `psyabx/arturbyrski.pl` i uprawnieniem **Contents: Read and write**.

## Nowa gra

```bash
python3 narzedzia/strona.py nowa-gra --gra moja-gra --nazwa "Moja gra" --pakiet com.psyabx.mojagra
```

Potem uzupełnij opisy w `dane/gry/moja-gra.json`, dodaj politykę prywatności (np. jako osobny plik HTML)
i wpisz jej adres w polu `polityka`. W repozytorium nowej gry skopiuj krok „Strona” z workflow wydania
Piżamersów i zmień `--gra`.

## Dla wirtualnego influencera i innych automatów

Stałe adresy do odpytywania:

- `https://arturbyrski.pl/api/wydania.json`: nowe wydania. Każdy wpis ma stałe `id`
  (`<gra>-<wersja>-<kod>`), więc automat zapamiętuje, które już opisał. Pole `_wydanie` zawiera
  notatki PL/EN, ścieżkę (`publiczne: true` tylko dla produkcji), adresy zrzutów i link do sklepu.
- `https://arturbyrski.pl/api/gry.json`: materiały prasowe wszystkich gier (opisy, okładki, zrzuty).
- `https://arturbyrski.pl/feed.xml`: RSS, np. do automatyzacji typu Zapier/Make.

Zasada: posty publiczne tylko o wydaniach z `publiczne: true`, bez danych dzieci i bez reklam
skierowanych do dzieci.

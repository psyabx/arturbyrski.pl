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
| `ortografia/<slug>/index.html`, `ortografia/index.html` | zasady pisowni (ó/u, rz/ż, ch/h) z `dane/ortografia/<slug>.json` |
| `sitemap.xml`, `robots.txt` | wyszukiwarki: lista stron do zaindeksowania |

Strony gier mają też adres kanoniczny, podgląd linku (Open Graph) i dane strukturalne schema.org
(gra, wydawca, wiek dzieci). Tytuł i opis w Google ustawia opcjonalne pole `seo` w danych gry:
`tytul`, `opis`, `kategoria` (`EducationalApplication` dla gier do nauki, inaczej `GameApplication`)
i `tematy` (frazy, których szukają rodzice, np. „nauka ortografii”). Bez tego pola używane są
nazwa gry i `opis_krotki`.

Plików wygenerowanych nie edytuj ręcznie. Zmień dane i uruchom `python3 narzedzia/strona.py zbuduj`
(albo tylko wypchnij zmianę danych: workflow „Zbuduj stronę” przebuduje stronę sam).

## Zasady ortografii

Strony w `ortografia/` przyciągają rodziców, którzy szukają w Google np. „ó czy u zasady”, i prowadzą do
gry Ortopotwory. Każda strona to jeden plik `dane/ortografia/<slug>.json`: reguły, przykłady, wyjątki,
ćwiczenie i pytania. Wyrazy zapisujemy jak w grze: litera do odgadnięcia w nawiasach, np. `st[ó]ł`,
a przykład z rodziną wyrazu jako `st[ó]ł|stoły`. Strony nigdy nie pokazują wyrazu z błędem.
Nowa strona: dodaj plik JSON i uruchom `python3 narzedzia/strona.py zbuduj`.

## Automatyczna aktualizacja po wydaniu gry

Workflow wydania w repozytorium gry (np. `psyabx/playgame`, plik `.github/workflows/release.yml`)
po udanej wysyłce do Google Play pobiera to repozytorium, uruchamia

```bash
python3 narzedzia/strona.py wydanie --gra szlafmyce --wersja 0.2.0 --kod 105 --sciezka internal \
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
Szlafmyców i zmień `--gra`.

## Dla wirtualnego influencera i innych automatów

Stałe adresy do odpytywania:

- `https://arturbyrski.pl/api/wydania.json`: nowe wydania. Każdy wpis ma stałe `id`
  (`<gra>-<wersja>-<kod>`), więc automat zapamiętuje, które już opisał. Pole `_wydanie` zawiera
  notatki PL/EN, ścieżkę (`publiczne: true` tylko dla produkcji), adresy zrzutów i link do sklepu.
- `https://arturbyrski.pl/api/gry.json`: materiały prasowe wszystkich gier (opisy, okładki, zrzuty).
- `https://arturbyrski.pl/feed.xml`: RSS, np. do automatyzacji typu Zapier/Make.

Zasada: posty publiczne tylko o wydaniach z `publiczne: true`, bez danych dzieci i bez reklam
skierowanych do dzieci.

## Statystyki odwiedzin

Strona liczy odwiedziny przez Cloudflare Web Analytics (bez ciasteczek i danych osobowych).
Token jest w `dane/statystyki.json` (`cloudflare_token`, pusty = statystyki wyłączone).
Generator wstawia skrypt między `<!-- statystyki:start -->` a `<!-- statystyki:koniec -->`
na każdej stronie, także w `index.html` i politykach prywatności. Po zmianie tokenu na `main`
workflow „Zbuduj stronę” przebuduje strony sam. Wyniki: dash.cloudflare.com → Analytics & Logs → Web Analytics.

## Gry na PC dla dorosłych (River Fly Shop)

Osobna ścieżka od gier dla dzieci. Dane: `dane/gry-pc/<slug>.json` (opisy PL/EN, mechaniki, galeria,
dziennik rozwoju). Generator: `narzedzia/gry_pc.py`, uruchamiany przez `python3 narzedzia/strona.py zbuduj`.
Te gry nie trafiają do kart na stronie głównej, do `api/*.json` ani do `feed.xml`.

| Adres (PL) | Adres (EN) | Co to jest |
| --- | --- | --- |
| `/gry/river-fly-shop/` | `/en/games/river-fly-shop/` | strona gry, `hreflang` pl/en, `x-default` = EN |
| `/gry/river-fly-shop/testy/` | `/en/games/river-fly-shop/playtest/` | zgłoszenie do testów przez e-mail (noindex) |
| `/gry/river-fly-shop/prywatnosc/` | `/en/games/river-fly-shop/privacy/` | prywatność zgłoszeń i statystyk |
| `/gry/river-fly-shop/feed.xml` | `/en/games/river-fly-shop/feed.xml` | dziennik rozwoju jako RSS |
| `/gry/river-fly-shop/z/<źródło>/` | `/en/games/river-fly-shop/from/<źródło>/` | kopia strony gry dla kampanii (noindex, kanoniczny = strona gry) |
| `/gry/` | | wszystkie gry: dla dzieci i na PC |

Zasady treści: tylko to, co działa w wersji testowej; plany w osobnej liście „W pracy”. Zrzuty z tymczasową
grafiką AI mają w danych `"ai": true`. Gdy mają to wszystkie zrzuty, strona pokazuje jeden znaczek
„tymczasowa grafika AI” przy filarach i uwagę nad galerią; w galerii mieszanej znaczek dostaje każdy zrzut z AI. Dziennik piszemy dla gracza
(co nowego można robić w grze), nie dla programisty. Postacie opisujemy tylko jako inspirowane prawdziwymi
wędkarzami, bez imion i danych osobowych.

**Wyszukiwarki:** `seo_tytul` (do około 60 znaków) i `seo_opis` (do około 155 znaków) trafiają do `<title>`, opisu strony
i podglądu przy udostępnianiu. `o_grze_tytul` to nagłówek sekcji „O grze”, a `pytania` (pary pytanie i odpowiedź) tworzą
sekcję „Częste pytania”. Każdy zrzut w galerii ma krótki podpis `opis` i dłuższy tekst zastępczy `alt`, który opisuje to,
co naprawdę widać na obrazie; bez pola `alt` strona używa podpisu. Dane strukturalne (gra, zwiastun, ścieżka nawigacji
i częste pytania) generator składa sam z tych samych pól. Zwiastun trafia do nich, gdy `trailer` ma pole `data`
(dzień publikacji filmu); długość filmu generator odczytuje z pliku MP4. Przy podmianie zwiastuna popraw `data`.

**Steam:** gdy gra będzie miała stronę w sklepie, wpisz numer aplikacji w `steam_app_id`. Przycisk pojawi
się wtedy sam, z UTM `utm_campaign=rfs-strona-gry` (EN: `rfs-strona-gry-en`). Przy `null` nie ma żadnego przycisku.

**Zwiastun:** sekcja „Zwiastun / Trailer” pojawia się (razem z pozycją w menu) dopiero po wpisaniu pola `trailer`:
`{"mp4": "img/gry/river-fly-shop/zwiastun.mp4", "plakat": "img/gry/river-fly-shop/zwiastun.jpg"}` (plik z tej domeny,
GitHub Pages przyjmuje pliki do 100 MB) albo `{"youtube": "<id filmu>", "plakat": "img/gry/river-fly-shop/zwiastun.jpg"}`.
YouTube wczytuje się dopiero po kliknięciu, z youtube-nocookie.com, więc samo wejście na stronę nie łączy się z Google.
Plakat jest obowiązkowy i lokalny. Film ze zrzutami gry ma domyślnie znaczek „tymczasowa grafika AI” (`"ai": false` go wyłącza).

**Zgłoszenia:** przycisk otwiera e-mail z tematem „River Fly Shop – testy” (EN: „River Fly Shop – playtest”).
W Gmailu warto ustawić filtr na oba tematy z jedną etykietą, żeby policzyć zgłoszenia.

### Źródła ruchu w Cloudflare Web Analytics

Cloudflare Web Analytics nie zapisuje parametrów UTM ani własnych zdarzeń
([FAQ](https://developers.cloudflare.com/web-analytics/faq/)). Dlatego:

- **Strony** widać osobno w panelu (filtr „Path”), np. `/gry/river-fly-shop/` i `/en/games/river-fly-shop/`.
- **Źródło** pokazuje „Referer”, ale aplikacje (Messenger, Reddit, YouTube na telefonie) i kody QR często go
  nie przekazują. W linkach publikowanych na zewnątrz używaj więc ścieżek kampanii, np.
  `https://arturbyrski.pl/gry/river-fly-shop/z/reddit/` albo `https://arturbyrski.pl/en/games/river-fly-shop/from/reddit/`.
  Wejścia widać w panelu jako osobną ścieżkę. Lista źródeł jest w polu `kampanie` (teraz: facebook, reddit,
  youtube, forum, qr); nowe źródło to nowy wpis i przebudowa strony.
- **Zainteresowanie testami** to wejścia na `/testy/` i `/playtest/`. To przybliżenie, nie liczba zgłoszeń:
  faktyczne zgłoszenia liczymy w Gmailu po temacie.

Czcionki stron PC: Alegreya (SIL Open Font License 1.1), pliki `fonty/Alegreya*.woff2` (podzbiór znaków PL/EN).

## Czcionka

`fonty/Grandstander.ttf` (licencja SIL Open Font License 1.1) jest serwowana z tej domeny,
żeby strona nie łączyła się z zewnętrznymi serwerami (np. Google Fonts).

# arturbyrski.pl: instrukcja dla agentów

Strona firmy Artur Byrski Link Technologies. Statyczny HTML na GitHub Pages: gałąź `main`
jest od razu produkcją (domena z `CNAME`). Szczegóły generatora i danych: `README.md`.

## Podłączenie

- Repozytorium: `psyabx/arturbyrski.pl` (GitHub). W sesji Claude Code w chmurze: dodaj je
  narzędziem `add_repo` (dostęp `push`), sklonuj płytko
  `git clone --depth 1 https://github.com/psyabx/arturbyrski.pl`.
- Pull requesty zakładaj przez REST (`gh api repos/psyabx/arturbyrski.pl/pulls -f ...`),
  bo GraphQL (`gh pr create`) jest w chmurze zablokowany. Przypisz `psyabx`.
- Domena arturbyrski.pl bywa zablokowana przez proxy chmury. Żywą stronę czytaj przez
  przeglądarkę na komputerze Artura albo sprawdzaj lokalnie: `python3 -m http.server` w katalogu repo.

## Zasady

- **Nic nie trafia na `main` bez akceptacji Artura.** Zawsze osobna gałąź `claude/...`
  i pull request. Scala Artur.
- Nie edytuj ręcznie plików wygenerowanych (strony gier, `/gry/`, `/en/`, `api/`, `feed.xml`,
  `sitemap.xml`, `ortografia/`). Zmieniaj dane w `dane/` i uruchom
  `python3 narzedzia/strona.py zbuduj`. Ręcznie edytuje się tylko `index.html` poza znacznikami
  `<!-- gry:start/koniec -->`, polityki prywatności i pliki CSS.
- Przed commitem: `python3 narzedzia/strona.py zbuduj`, a po commicie drugi raz. `git status`
  ma być czysty, bo inaczej workflow „Zbuduj stronę” odrzuci PR.
- Sprawdź strony w Chromium (Playwright) na 1366 px i 390 px: brak 404 i brak poziomego
  przewijania. Obejrzyj zrzuty, zanim pokażesz je Arturowi.
- Analityka: tylko Cloudflare Web Analytics (token w `dane/statystyki.json`). Bez Google
  Analytics, bez ciasteczek, bez zewnętrznych czcionek i skryptów.

## Dwie osobne ścieżki

- **Gry dla dzieci** (Ortopotwory, Szlafmyce): `dane/gry/*.json`, strona główna, `feed.xml`,
  `api/`. Przekaz „bez reklam, bez zbierania danych, offline” zostaje bez zmian. Nie mieszaj
  tu treści dla dorosłych.
- **River Fly Shop** (gra na PC w produkcji): `dane/gry-pc/river-fly-shop.json`, generator
  `narzedzia/gry_pc.py`, styl `styl-pc.css`. Adresy: `/gry/river-fly-shop/` (PL) i
  `/en/games/river-fly-shop/` (EN), zgłoszenia `testy/` i `playtest/`, prywatność, RSS,
  ścieżki kampanii `z/<źródło>/` i `from/<źródło>/`.

## Treść River Fly Shop

- Tylko to, co naprawdę działa w wersji testowej. Plany idą do listy „W pracy”.
- Nazwa zawsze jako „tytuł roboczy” (EUIPO niesprawdzone).
- Postacie tylko „inspirowane prawdziwymi wędkarzami”, bez imion i danych osobowych.
- Zrzuty z tymczasową grafiką AI mają `"ai": true`. Gdy mają to wszystkie zrzuty, strona pokazuje jeden
  wspólny znaczek przy filarach i uwagę nad galerią; w galerii mieszanej znaczek dostaje każdy zrzut z AI. Zrzuty mają pochodzić
  z gry na PC Artura (pełna grafika, bez interfejsu), nie z renderu w chmurze.
- Dziennik rozwoju piszemy dla gracza: co nowego można robić w grze.
- Przycisk Steam i sekcja zwiastuna pojawiają się dopiero po wpisaniu `steam_app_id` /
  `trailer` w danych. Nie pokazuj nieaktywnych przycisków ani „wkrótce na Steamie”.
- Zgłoszenia do testów tylko e-mailem (mailto) z informacją o prywatności. Bez formularzy
  wysyłających dane do zewnętrznych firm.

## Wyszukiwarki i czaty AI

- Google Search Console: właściwość domeny arturbyrski.pl (rekord TXT w DNS OVH), mapa `sitemap.xml` zgłoszona.
- Bing Webmaster Tools: weryfikacja plikiem `BingSiteAuth.xml`, mapa zgłoszona. Bing zasila ChatGPT i Copilota;
  cytowania widać w zakładce „AI Performance”.
- Nie usuwaj plików `BingSiteAuth.xml` ani `750996d55b19827dda883a485b7a8196.txt` (klucz IndexNow).
- `robots.txt` i `llms.txt` generuje `narzedzia/strona.py` (lista botów `ROBOTY_AI`). Nie edytuj ich ręcznie.
  `llms.txt` powstaje z tytułów i opisów istniejących stron, więc nie dopisuj tam nowych treści.
- Po scaleniu zmian w treści uruchom `python3 narzedzia/indexnow.py --od RRRR-MM-DD`
  (najpierw `--proba`, żeby zobaczyć listę adresów).

# Formularze strony dla nauczycieli (Google Apps Script + Arkusz Google)

Strona `/gry/ortopotwory/dla-nauczycieli/` jest statyczna (GitHub Pages), więc zgłoszenia i opinie
odbiera ten skrypt. Działa na koncie Google właściciela strony: zapisuje wiersze w arkuszu
i wysyła powiadomienie na Gmaila. W kodzie strony nie ma żadnych haseł ani kluczy, tylko publiczny
adres skryptu.

## Wdrożenie (około 5 minut, raz)

1. Na koncie Google, na które mają przychodzić zgłoszenia, utwórz nowy Arkusz Google, np.
   „Ortopotwory – testerzy”.
2. W arkuszu: **Rozszerzenia → Apps Script**. Usuń przykładowy kod i wklej całą zawartość
   `formularze.gs`. Zapisz (ikona dyskietki).
3. Na górze wybierz funkcję `przygotuj` i kliknij **Uruchom**. Google poprosi o uprawnienia
   (arkusz i wysyłanie e-maili w Twoim imieniu): zaakceptuj. Powstaną zakładki Zgłoszenia, Opinie,
   Zdarzenia i Podsumowanie.
4. **Wdróż → Nowe wdrożenie → typ: Aplikacja internetowa**.
   - Wykonaj jako: **Ja**
   - Kto ma dostęp: **Każdy**
   Kliknij **Wdróż** i skopiuj adres kończący się na `/exec`.
5. Otwórz ten adres w przeglądarce. Powinien pokazać `{"ok":true,"info":"Formularze Ortopotworów działają."}`.
6. Wklej adres w `dane/nauczyciele.json` w polu `formularz_url` (albo przekaż go Claude'owi) i
   przebuduj stronę: `python3 narzedzia/strona.py zbuduj`.
7. Usuwanie starych danych: w Apps Script **Wyzwalacze → Dodaj wyzwalacz**, funkcja `usunStare`,
   źródło: według czasu, raz dziennie. Okresy są w stałej `PRZECHOWYWANIE` (12 miesięcy zgłoszenia,
   24 miesiące opinie i liczniki).

Opcjonalnie: inny adres powiadomień ustawisz w **Ustawienia projektu → Właściwości skryptu**,
klucz `ODBIORCA`. Domyślnie powiadomienia idą na konto, które wdrożyło skrypt.

Po każdej zmianie kodu: **Wdróż → Zarządzaj wdrożeniami → edytuj → Wersja: nowa**. Adres `/exec`
się nie zmienia.

## Co zapisuje

| Zakładka | Kolumny | Dane osobowe |
| --- | --- | --- |
| Zgłoszenia | data, imię, e-mail, rola, wiadomość, zgoda (z datą), utm_*, odsyłacz, status, kod_wyslany | tak (imię, e-mail) |
| Opinie | data, rola, 2 odpowiedzi, poprawki, uwagi, utm_* | nie są wymagane |
| Zdarzenia | data, nazwa (`klik_zglos`, `klik_play`), utm_* | nie |

Kolumny `status` i `kod_wyslany` są dla Ciebie: wpisz tam np. „kod wysłany” i datę, gdy ręcznie
wyślesz kod promocyjny Google Play. Skrypt nie wysyła kodów sam.

## Zabezpieczenia

- Walidacja po stronie przeglądarki i ponownie w skrypcie (wymagane pola, format e-maila, lista ról
  i odpowiedzi, limity długości).
- Pułapka na boty: ukryte pole `strona_www` i minimalny czas wypełniania 3 s. Takie zgłoszenia nie
  są zapisywane.
- Limit 20 formularzy i 300 zdarzeń na 10 minut dla całej strony (chroni arkusz i dzienny limit
  e-maili Google) oraz pominięcie powtórnego zgłoszenia z tego samego adresu w ciągu godziny.
- Tekst zaczynający się od `=`, `+`, `-`, `@` jest zapisywany jako zwykły tekst, nie formuła.
- Skrypt nie zna adresów IP i ich nie zapisuje.

## Testy

`node narzedzia/apps-script/test_formularze.js` sprawdza walidację, pułapki, czyszczenie UTM
i ochronę przed formułami. Części zależnej od Google (zapis w arkuszu, e-mail) nie da się sprawdzić
lokalnie: po wdrożeniu wyślij jedno próbne zgłoszenie i jedną opinię ze strony.

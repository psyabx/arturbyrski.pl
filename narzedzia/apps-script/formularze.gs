/**
 * Obsługa formularzy strony /gry/ortopotwory/dla-nauczycieli/ (Google Apps Script).
 *
 * Skrypt jest przypięty do Arkusza Google właściciela strony. Przyjmuje POST z przeglądarki,
 * sprawdza dane, zapisuje wiersz w arkuszu i wysyła powiadomienie e-mail do właściciela.
 * Wdrożenie krok po kroku: narzedzia/apps-script/README.md.
 *
 * Typy wiadomości (pole "typ"):
 *  - "zgloszenie": imię, e-mail, rola, wiadomość, zgoda + utm_*   -> arkusz „Zgłoszenia” + e-mail
 *  - "opinia":     rola, 2 pytania zamknięte, poprawki, uwagi + utm_* -> arkusz „Opinie” + e-mail
 *  - "zdarzenie":  nazwa kliknięcia + utm_* (bez danych osobowych)   -> arkusz „Zdarzenia”
 *
 * Nie zapisujemy adresów IP (Apps Script ich nie zna) ani niczego poza polami poniżej.
 */

var ARKUSZE = {
  zgloszenie: {
    nazwa: "Zgłoszenia",
    kolumny: ["data", "imie", "email", "rola", "wiadomosc", "zgoda", "utm_source", "utm_medium",
      "utm_campaign", "utm_content", "utm_term", "odsylacz", "status", "kod_wyslany"]
  },
  opinia: {
    nazwa: "Opinie",
    kolumny: ["data", "rola", "zrozumiale", "wykorzystanie", "poprawki", "uwagi", "utm_source",
      "utm_medium", "utm_campaign", "utm_content", "utm_term", "odsylacz"]
  },
  zdarzenie: {
    nazwa: "Zdarzenia",
    kolumny: ["data", "nazwa", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]
  }
};

var ROLE = ["", "nauczyciel", "terapeuta pedagogiczny", "pedagog", "rodzic", "inna"];
var ODPOWIEDZI = ["Tak", "Raczej tak", "Raczej nie", "Nie", "Trudno powiedzieć"];
var ZDARZENIA = ["klik_zglos", "klik_play"];
var MIN_CZAS_MS = 3000;
// Limity na 10 minut dla całej strony: chronią arkusz i limit e-maili Google (100/dzień).
var LIMIT_FORMULARZY = 20;
var LIMIT_ZDARZEN = 300;
// Okres przechowywania (miesiące), używany przez usunStare().
var PRZECHOWYWANIE = { zgloszenie: 12, opinia: 24, zdarzenie: 24 };

var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

/** Czyści tekst: przycina, usuwa znaki sterujące, ogranicza długość. */
function tekst(v, max) {
  return String(v == null ? "" : v)
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .trim()
    .slice(0, max);
}

/** Parametr kampanii: tylko litery, cyfry, _ . - (jak w przeglądarce). */
function znacznik(v) {
  return String(v == null ? "" : v).replace(/[^\w.\-]/g, "").slice(0, 64);
}

/** Arkusz nie może potraktować tekstu jak formuły (=, +, -, @). */
function bezFormul(v) {
  return /^[=+\-@\t\r]/.test(v) ? "'" + v : v;
}

/**
 * Sprawdza i normalizuje dane. Zwraca { ok: true, typ, wiersz } albo { ok: false, blad, cicho }.
 * cicho = true dla botów: odpowiadamy błędem, ale nie zapisujemy i nie wysyłamy e-maila.
 */
function sprawdzDane(d, teraz) {
  if (!d || typeof d !== "object") return { ok: false, blad: "Nieprawidłowe dane." };
  var typ = d.typ;
  if (!ARKUSZE[typ]) return { ok: false, blad: "Nieznany formularz." };
  var utm = {
    utm_source: znacznik(d.utm_source), utm_medium: znacznik(d.utm_medium),
    utm_campaign: znacznik(d.utm_campaign), utm_content: znacznik(d.utm_content),
    utm_term: znacznik(d.utm_term), odsylacz: znacznik(d.odsylacz)
  };
  var data = (teraz || new Date()).toISOString();

  if (typ === "zdarzenie") {
    if (ZDARZENIA.indexOf(d.nazwa) < 0) return { ok: false, blad: "Nieznane zdarzenie." };
    return { ok: true, typ: typ, wiersz: [data, d.nazwa, utm.utm_source, utm.utm_medium,
      utm.utm_campaign, utm.utm_content, utm.utm_term] };
  }

  // Pułapka na boty: ukryte pole wypełnione albo formularz wysłany w mniej niż 3 s.
  if (tekst(d.strona_www, 200) || !(Number(d.czas_ms) >= MIN_CZAS_MS)) {
    return { ok: false, blad: "Nie udało się wysłać formularza. Spróbuj ponownie.", cicho: true };
  }
  var rola = tekst(d.rola, 40);
  if (ROLE.indexOf(rola) < 0) return { ok: false, blad: "Wybierz rolę z listy." };

  if (typ === "zgloszenie") {
    var imie = tekst(d.imie, 60);
    var email = tekst(d.email, 120).toLowerCase();
    var wiadomosc = tekst(d.wiadomosc, 2000);
    if (!imie) return { ok: false, blad: "Podaj imię." };
    if (!EMAIL.test(email)) return { ok: false, blad: "Sprawdź adres e-mail." };
    if (d.zgoda !== "tak") return { ok: false, blad: "Zaznacz zgodę na kontakt." };
    return { ok: true, typ: typ, email: email, wiersz: [data, imie, email, rola, wiadomosc,
      "tak (" + data.slice(0, 10) + ")", utm.utm_source, utm.utm_medium, utm.utm_campaign,
      utm.utm_content, utm.utm_term, utm.odsylacz, "nowe", ""] };
  }

  // opinia
  var zrozumiale = tekst(d.zrozumiale, 40);
  var wykorzystanie = tekst(d.wykorzystanie, 40);
  var poprawki = tekst(d.poprawki, 3000);
  var uwagi = tekst(d.uwagi, 3000);
  if (ODPOWIEDZI.indexOf(zrozumiale) < 0 || ODPOWIEDZI.indexOf(wykorzystanie) < 0) {
    return { ok: false, blad: "Odpowiedz na oba pytania zamknięte." };
  }
  if (!poprawki) return { ok: false, blad: "Napisz, co poprawić w pierwszej kolejności." };
  return { ok: true, typ: typ, wiersz: [data, rola, zrozumiale, wykorzystanie, poprawki, uwagi,
    utm.utm_source, utm.utm_medium, utm.utm_campaign, utm.utm_content, utm.utm_term, utm.odsylacz] };
}

/** Treść powiadomienia e-mail dla właściciela. */
function trescPowiadomienia(wynik) {
  var kol = ARKUSZE[wynik.typ].kolumny;
  var linie = kol.map(function (k, i) { return k + ": " + wynik.wiersz[i]; })
    .filter(function (l) { return !/: $/.test(l); });
  var temat = wynik.typ === "zgloszenie"
    ? "Ortopotwory: nowe zgłoszenie do testów (" + wynik.wiersz[1] + ")"
    : "Ortopotwory: nowa opinia po teście";
  return { temat: temat, tresc: linie.join("\n") + "\n\nArkusz: " + adresArkusza() };
}

// ---------- część zależna od Google (nie testowana lokalnie) ----------

function adresArkusza() {
  try { return SpreadsheetApp.getActiveSpreadsheet().getUrl(); } catch (e) { return ""; }
}

function odpowiedz(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function arkusz(typ) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var a = ss.getSheetByName(ARKUSZE[typ].nazwa);
  if (!a) {
    a = ss.insertSheet(ARKUSZE[typ].nazwa);
    a.appendRow(ARKUSZE[typ].kolumny);
    a.setFrozenRows(1);
  }
  return a;
}

/** Prosty limit: licznik w pamięci podręcznej skryptu na 10-minutowe okno. */
function ponadLimit(klucz, limit) {
  var cache = CacheService.getScriptCache();
  var okno = klucz + "_" + Math.floor(Date.now() / 600000);
  var n = Number(cache.get(okno) || 0) + 1;
  cache.put(okno, String(n), 700);
  return n > limit;
}

function doPost(e) {
  var d;
  try {
    d = JSON.parse(e && e.postData ? e.postData.contents : "");
  } catch (err) {
    return odpowiedz({ ok: false, blad: "Nieprawidłowe dane." });
  }
  var wynik = sprawdzDane(d);
  if (!wynik.ok) return odpowiedz({ ok: false, blad: wynik.blad });

  var formularz = wynik.typ !== "zdarzenie";
  if (ponadLimit(formularz ? "formularze" : "zdarzenia", formularz ? LIMIT_FORMULARZY : LIMIT_ZDARZEN)) {
    return odpowiedz({ ok: false, blad: "Za dużo zgłoszeń naraz. Spróbuj ponownie za kilka minut." });
  }
  if (wynik.typ === "zgloszenie") {
    // To samo zgłoszenie wysłane dwa razy w ciągu godziny zapisujemy raz.
    var cache = CacheService.getScriptCache();
    var klucz = "email_" + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, wynik.email));
    if (cache.get(klucz)) return odpowiedz({ ok: true, powtorka: true });
    cache.put(klucz, "1", 3600);
  }

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    arkusz(wynik.typ).appendRow(wynik.wiersz.map(function (v) { return bezFormul(String(v)); }));
  } catch (err) {
    return odpowiedz({ ok: false, blad: "Nie udało się zapisać. Spróbuj ponownie za chwilę." });
  } finally {
    lock.releaseLock();
  }

  if (formularz) {
    // Zapis w arkuszu już jest, więc błąd poczty nie oznacza utraty zgłoszenia.
    try {
      var p = trescPowiadomienia(wynik);
      var opcje = {};
      if (wynik.typ === "zgloszenie") opcje.replyTo = wynik.email;
      MailApp.sendEmail(odbiorca(), p.temat, p.tresc, opcje);
    } catch (err) {
      console.error("Powiadomienie e-mail nie wyszło: " + err);
    }
  }
  return odpowiedz({ ok: true });
}

/** GET pod adresem skryptu: szybkie sprawdzenie, że wdrożenie działa. */
function doGet() {
  return odpowiedz({ ok: true, info: "Formularze Ortopotworów działają." });
}

function odbiorca() {
  return PropertiesService.getScriptProperties().getProperty("ODBIORCA")
    || Session.getEffectiveUser().getEmail();
}

/** Uruchom raz ręcznie: tworzy arkusze i zakładkę „Podsumowanie” z licznikami według źródła. */
function przygotuj() {
  Object.keys(ARKUSZE).forEach(arkusz);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var p = ss.getSheetByName("Podsumowanie") || ss.insertSheet("Podsumowanie", 0);
  p.clear();
  p.getRange("A1").setValue("Zgłoszenia według źródła (utm_source / utm_campaign)");
  p.getRange("A2").setFormula("=QUERY('Zgłoszenia'!A:L, \"select G, I, count(A) where A is not null group by G, I label count(A) 'zgłoszenia'\", 1)");
  p.getRange("E1").setValue("Kliknięcia według zdarzenia i źródła");
  p.getRange("E2").setFormula("=QUERY(Zdarzenia!A:G, \"select B, C, count(A) where A is not null group by B, C label count(A) 'kliknięcia'\", 1)");
  p.getRange("I1").setValue("Opinie według źródła");
  p.getRange("I2").setFormula("=QUERY(Opinie!A:L, \"select G, count(A) where A is not null group by G label count(A) 'opinie'\", 1)");
}

/** Usuwa wiersze starsze niż PRZECHOWYWANIE. Ustaw wyzwalacz czasowy: raz dziennie. */
function usunStare() {
  Object.keys(ARKUSZE).forEach(function (typ) {
    var a = arkusz(typ);
    var granica = new Date();
    granica.setMonth(granica.getMonth() - PRZECHOWYWANIE[typ]);
    var dane = a.getDataRange().getValues();
    for (var i = dane.length - 1; i >= 1; i--) {
      var d = new Date(dane[i][0]);
      if (!isNaN(d) && d < granica) a.deleteRow(i + 1);
    }
  });
}

// Testy lokalne (node narzedzia/apps-script/test_formularze.js) korzystają z czystych funkcji.
if (typeof module !== "undefined") {
  module.exports = { sprawdzDane: sprawdzDane, bezFormul: bezFormul, trescPowiadomienia: trescPowiadomienia, ARKUSZE: ARKUSZE };
}

/* Formularze strony dla nauczycieli: zgłoszenie do testów i opinia po teście.
 *
 * - Dane idą do skryptu Google Apps Script (adres w <body data-formularz-url>, ustawiany
 *   w dane/nauczyciele.json). Sukces pokazujemy dopiero, gdy skrypt potwierdzi zapis.
 * - Parametry utm_* czytamy z adresu strony i wysyłamy razem z formularzem. Nic nie
 *   zapisujemy w przeglądarce (bez ciasteczek, localStorage i sessionStorage).
 * - Liczniki kliknięć (data-zdarzenie) wysyłają tylko nazwę zdarzenia i utm_*, bez danych osobowych.
 */
(function () {
  "use strict";

  var ENDPOINT = document.body.getAttribute("data-formularz-url") || "";
  var KONTAKT = "art.byrski@gmail.com";
  var MIN_CZAS_MS = 3000; // szybciej wypełnia tylko bot
  var UTM = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
  var start = Date.now();

  function czysc(v) {
    return String(v || "").replace(/[^\w.\-]/g, "").slice(0, 64);
  }

  function zrodlo() {
    var z = {};
    var p = new URLSearchParams(window.location.search);
    UTM.forEach(function (k) { z[k] = czysc(p.get(k)); });
    var odsylacz = "";
    try {
      if (document.referrer) {
        var host = new URL(document.referrer).hostname;
        if (host && host !== window.location.hostname) odsylacz = czysc(host);
      }
    } catch (e) { /* nieprawidłowy referrer: pomijamy */ }
    z.odsylacz = odsylacz;
    return z;
  }

  var ZRODLO = zrodlo();

  function wyslijZdarzenie(nazwa) {
    if (!ENDPOINT || !navigator.sendBeacon) return;
    var dane = { typ: "zdarzenie", nazwa: nazwa };
    UTM.forEach(function (k) { dane[k] = ZRODLO[k]; });
    try {
      navigator.sendBeacon(ENDPOINT, new Blob([JSON.stringify(dane)], { type: "text/plain" }));
    } catch (e) { /* licznik nie może psuć strony */ }
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target.closest ? ev.target.closest("[data-zdarzenie]") : null;
    if (el) wyslijZdarzenie(el.getAttribute("data-zdarzenie"));
  });

  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  function bladPola(form, kontrolka, tekst) {
    var id = kontrolka.id || (kontrolka.closest("fieldset.pytanie") || {}).id;
    var p = id ? form.querySelector("#" + id + "-blad") : null;
    var cel = kontrolka.type === "radio" ? kontrolka.closest("fieldset.pytanie") : kontrolka;
    if (tekst) {
      cel.setAttribute("aria-invalid", "true");
      if (p) { p.textContent = tekst; p.hidden = false; }
    } else {
      cel.removeAttribute("aria-invalid");
      if (p) { p.textContent = ""; p.hidden = true; }
    }
  }

  function sprawdz(form) {
    var bledy = [];
    function test(el, tekst) {
      bladPola(form, el, tekst);
      if (tekst) bledy.push(el);
    }
    form.querySelectorAll("input[type=text][required], textarea[required]").forEach(function (el) {
      test(el, el.value.trim() ? "" : "To pole jest wymagane.");
    });
    form.querySelectorAll("input[type=email]").forEach(function (el) {
      var v = el.value.trim();
      test(el, !v ? "Podaj adres e-mail." : EMAIL.test(v) ? "" : "Sprawdź adres e-mail, np. imie@szkola.pl.");
    });
    form.querySelectorAll("input[type=checkbox][required]").forEach(function (el) {
      test(el, el.checked ? "" : "Zaznacz zgodę, żebyśmy mogli odpisać.");
    });
    form.querySelectorAll("fieldset.pytanie").forEach(function (fs) {
      var radio = fs.querySelector("input[type=radio]");
      var wybrany = fs.querySelector("input[type=radio]:checked");
      bladPola(form, radio, wybrany ? "" : "Wybierz jedną odpowiedź.");
      if (!wybrany) bledy.push(radio);
    });
    return bledy;
  }

  function komunikat(form, tekst, rodzaj) {
    var k = form.querySelector(".komunikat[role=status]");
    k.className = "komunikat " + (rodzaj || "");
    k.textContent = "";
    if (rodzaj === "blad") {
      k.appendChild(document.createTextNode(tekst + " Możesz też napisać na "));
      var a = document.createElement("a");
      a.href = "mailto:" + KONTAKT;
      a.textContent = KONTAKT;
      k.appendChild(a);
      k.appendChild(document.createTextNode("."));
    } else {
      k.textContent = tekst;
    }
    k.focus();
  }

  function dane(form) {
    var d = {};
    new FormData(form).forEach(function (v, k) { d[k] = typeof v === "string" ? v.trim() : ""; });
    UTM.forEach(function (k) { d[k] = ZRODLO[k]; });
    d.odsylacz = ZRODLO.odsylacz;
    d.czas_ms = Date.now() - start;
    return d;
  }

  function wyslij(form, ev) {
    ev.preventDefault();
    if (!ENDPOINT) return;
    var przycisk = form.querySelector("button[type=submit]");
    if (przycisk.disabled) return; // trwa wysyłanie
    var bledy = sprawdz(form);
    if (bledy.length) {
      komunikat(form, "Popraw zaznaczone pola.", "blad-lokalny");
      bledy[0].focus();
      return;
    }
    var d = dane(form);
    if (d.strona_www || d.czas_ms < MIN_CZAS_MS) {
      // Bot albo przypadkowe, natychmiastowe wysłanie: nie wysyłamy, ale też nie udajemy sukcesu.
      komunikat(form, "Nie udało się wysłać formularza. Odczekaj chwilę i spróbuj ponownie.", "blad");
      return;
    }
    przycisk.disabled = true;
    var tekstPrzycisku = przycisk.textContent;
    przycisk.textContent = "Wysyłanie…";
    var kontroler = window.AbortController ? new AbortController() : null;
    var limit = setTimeout(function () { if (kontroler) kontroler.abort(); }, 20000);

    // text/plain nie wymaga zapytania wstępnego CORS, a Apps Script i tak czyta surową treść.
    fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=utf-8" },
      body: JSON.stringify(d),
      redirect: "follow",
      signal: kontroler ? kontroler.signal : undefined
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (odp) {
        if (odp && odp.ok) {
          form.reset();
          start = Date.now();
          form.querySelectorAll("[aria-invalid]").forEach(function (el) { el.removeAttribute("aria-invalid"); });
          komunikat(form, form.getAttribute("data-sukces"), "ok");
        } else {
          komunikat(form, (odp && odp.blad) || "Nie udało się zapisać formularza.", "blad");
        }
      })
      .catch(function () {
        komunikat(form, "Nie udało się połączyć z serwerem. Twoje odpowiedzi są nadal w formularzu, spróbuj ponownie za chwilę.", "blad");
      })
      .then(function () {
        clearTimeout(limit);
        przycisk.disabled = false;
        przycisk.textContent = tekstPrzycisku;
      });
  }

  document.querySelectorAll("form[data-formularz]").forEach(function (form) {
    form.addEventListener("submit", function (ev) { wyslij(form, ev); });
    // Błąd znika już podczas pisania (zdarzenie input), a nie po opuszczeniu pola: inaczej
    // komunikat znikałby w chwili kliknięcia „Wyślij”, przycisk by podskoczył i klik by przepadł.
    function popraw(ev) {
      var el = ev.target;
      if (!el.getAttribute("aria-invalid") && el.type !== "radio") return;
      var ok = el.type === "checkbox" ? el.checked : el.type === "radio" ? true
        : el.type === "email" ? EMAIL.test(el.value.trim()) : !!el.value.trim();
      if (ok) bladPola(form, el, "");
    }
    form.addEventListener("input", popraw);
    form.addEventListener("change", popraw);
  });
})();

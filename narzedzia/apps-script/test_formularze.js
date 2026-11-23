// Testy czystej logiki skryptu formularzy: node narzedzia/apps-script/test_formularze.js
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const kod = fs.readFileSync(path.join(__dirname, "formularze.gs"), "utf8");
const modul = { exports: {} };
vm.runInNewContext(kod, { module: modul, console });
const { sprawdzDane, bezFormul, trescPowiadomienia } = modul.exports;
const teraz = new Date("2026-11-22T10:00:00Z");
const zgl = (x) => Object.assign({ typ: "zgloszenie", imie: "Anna", email: "Anna@Szkola.pl", rola: "nauczyciel",
  wiadomosc: "Uczę w klasie 3", zgoda: "tak", strona_www: "", czas_ms: 12000,
  utm_source: "email", utm_medium: "outreach", utm_campaign: "teacher_testing" }, x);
const op = (x) => Object.assign({ typ: "opinia", rola: "", zrozumiale: "Tak", wykorzystanie: "Raczej tak",
  poprawki: "Więcej dyktand", uwagi: "", czas_ms: 9000, utm_source: "email" }, x);
let n = 0;
function t(nazwa, f) { f(); n++; console.log("ok  " + nazwa); }

t("poprawne zgłoszenie z UTM", () => {
  const w = sprawdzDane(zgl(), teraz);
  assert.ok(w.ok);
  assert.strictEqual(w.wiersz[2], "anna@szkola.pl");
  assert.strictEqual(JSON.stringify(w.wiersz.slice(6, 9)), JSON.stringify(["email", "outreach", "teacher_testing"]));
  assert.strictEqual(w.wiersz[5], "tak (2026-11-22)");
});
t("brak imienia", () => assert.strictEqual(sprawdzDane(zgl({ imie: "  " })).ok, false));
t("zły e-mail", () => assert.strictEqual(sprawdzDane(zgl({ email: "anna@" })).ok, false));
t("brak zgody", () => assert.strictEqual(sprawdzDane(zgl({ zgoda: "" })).ok, false));
t("rola spoza listy", () => assert.strictEqual(sprawdzDane(zgl({ rola: "dyrektor" })).ok, false));
t("pułapka: ukryte pole", () => { const w = sprawdzDane(zgl({ strona_www: "http://spam" })); assert.ok(!w.ok && w.cicho); });
t("pułapka: za szybko", () => { const w = sprawdzDane(zgl({ czas_ms: 800 })); assert.ok(!w.ok && w.cicho); });
t("pułapka: brak czasu", () => assert.ok(sprawdzDane(zgl({ czas_ms: undefined })).cicho));
t("UTM oczyszczone", () => {
  const w = sprawdzDane(zgl({ utm_source: "<script>alert(1)</script>", utm_campaign: "a".repeat(200) }), teraz);
  assert.strictEqual(w.wiersz[6], "scriptalert1script");
  assert.strictEqual(w.wiersz[8].length, 64);
});
t("długie pola przycięte", () => assert.strictEqual(sprawdzDane(zgl({ wiadomosc: "x".repeat(5000) })).wiersz[4].length, 2000));
t("poprawna opinia", () => assert.ok(sprawdzDane(op(), teraz).ok));
t("opinia bez odpowiedzi zamkniętej", () => assert.ok(!sprawdzDane(op({ zrozumiale: "Może" })).ok));
t("opinia bez poprawek", () => assert.ok(!sprawdzDane(op({ poprawki: "" })).ok));
t("zdarzenie z listy", () => assert.strictEqual(JSON.stringify(sprawdzDane({ typ: "zdarzenie", nazwa: "klik_play", utm_source: "email" }, teraz).wiersz.slice(1, 3)), JSON.stringify(["klik_play", "email"])));
t("zdarzenie nieznane", () => assert.ok(!sprawdzDane({ typ: "zdarzenie", nazwa: "imie=Anna" }).ok));
t("nieznany typ", () => assert.ok(!sprawdzDane({ typ: "x" }).ok));
t("formuły neutralizowane", () => { assert.strictEqual(bezFormul("=HYPERLINK(1)"), "'=HYPERLINK(1)"); assert.strictEqual(bezFormul("Anna"), "Anna"); });
t("treść powiadomienia", () => {
  const p = trescPowiadomienia(sprawdzDane(zgl(), teraz));
  assert.ok(p.temat.includes("Anna"));
  assert.ok(p.tresc.includes("utm_campaign: teacher_testing"));
});
console.log(`\n${n} testów przeszło`);

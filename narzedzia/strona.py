#!/usr/bin/env python3
"""Generator strony arturbyrski.pl z danych gier (bez zewnętrznych bibliotek).

Źródło prawdy: dane/gry/<slug>.json (jedna gra = jeden plik).
Wynik (commitowany, bo GitHub Pages serwuje gałąź main):
  - index.html            sekcja między <!-- gry:start --> i <!-- gry:koniec -->
  - gry/<slug>/index.html strona gry z wersją, zrzutami i historią zmian
  - api/gry.json          wszystkie gry i ich najnowsze wersje (dla automatów, np. influencera)
  - api/wydania.json      JSON Feed 1.1 z wydaniami, od najnowszego
  - feed.xml              RSS 2.0 z wydaniami
  - ortografia/<slug>/index.html i ortografia/index.html  zasady pisowni z dane/ortografia/*.json
  - sitemap.xml, robots.txt  dla wyszukiwarek (lista stron i adres mapy)
  - skrypt statystyk Cloudflare Web Analytics (bez ciasteczek) między <!-- statystyki:start -->
    i <!-- statystyki:koniec --> na każdej stronie, jeśli dane/statystyki.json ma token

Użycie:
  python3 narzedzia/strona.py zbuduj
  python3 narzedzia/strona.py wydanie --gra pizamersi --wersja 0.2.0 --kod 105 \
      --sciezka internal --notatki-pl co-nowego/pl.txt --notatki-en co-nowego/en.txt \
      [--zrzuty katalog_z_png] [--data 2026-11-08]
  python3 narzedzia/strona.py nowa-gra --gra nowa-gra --nazwa "Nowa gra" [--pakiet com.psyabx.nowagra]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import shutil
import sys
from email.utils import format_datetime
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
DANE = KORZEN / "dane" / "gry"
DANE_ORTO = KORZEN / "dane" / "ortografia"
ADRES = "https://arturbyrski.pl"
FIRMA = "Artur Byrski Link Technologies"
ZNACZNIK_START = "<!-- gry:start -->"
ZNACZNIK_KONIEC = "<!-- gry:koniec -->"
STAT_START = "<!-- statystyki:start -->"
STAT_KONIEC = "<!-- statystyki:koniec -->"
STRONY_RECZNE = ["index.html", "polityka-prywatnosci.html", "polityka-prywatnosci-ortopotwory.html"]
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

SCIEZKI = {
    "internal": ("testy wewnętrzne", "internal testing"),
    "alpha": ("testy zamknięte", "closed testing"),
    "beta": ("testy otwarte", "open testing"),
    "production": ("dostępna w Google Play", "available on Google Play"),
}


def e(tekst: str) -> str:
    return html.escape(str(tekst), quote=True)


def wczytaj_gry() -> list[dict]:
    gry = []
    for plik in sorted(DANE.glob("*.json")):
        gra = json.loads(plik.read_text(encoding="utf-8"))
        if gra.get("slug") != plik.stem:
            sys.exit(f"{plik}: pole slug musi być równe nazwie pliku ({plik.stem})")
        gra["wydania"] = sorted(gra.get("wydania", []), key=lambda w: w["kod"], reverse=True)
        gry.append(gra)
    gry.sort(key=lambda g: (g.get("kolejnosc", 999), g["nazwa"]))
    return gry


def zapisz_gre(gra: dict) -> None:
    plik = DANE / f"{gra['slug']}.json"
    plik.write_text(json.dumps(gra, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def link_sklepu(gra: dict, zrodlo: str = "strona") -> str | None:
    """Link do Google Play pokazujemy dopiero, gdy jest wydanie produkcyjne.

    Parametry utm_* pozwalają w Play Console (raport pozyskania) sprawdzić,
    ile instalacji przyszło ze strony, bez żadnych narzędzi śledzących.
    """
    if gra.get("pakiet") and any(w["sciezka"] == "production" for w in gra["wydania"]):
        return (f"https://play.google.com/store/apps/details?id={gra['pakiet']}"
                f"&utm_source=arturbyrski.pl&utm_medium=strona&utm_campaign={zrodlo}")
    return None


def adres(sciezka: str) -> str:
    return f"{ADRES}/{sciezka.lstrip('/')}"


def data_pl(iso: str) -> str:
    miesiace = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
                "sierpnia", "września", "października", "listopada", "grudnia"]
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {miesiace[d.month - 1]} {d.year}"


# ---------- SEO ----------

def jsonld(dane: dict | list) -> str:
    """Dane strukturalne schema.org. Zamiana "</" chroni przed zamknięciem <script> w tekście."""
    tekst = json.dumps(dane, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f'<script type="application/ld+json">\n{tekst}\n</script>'


def wydawca() -> dict:
    return {"@type": "Organization", "@id": ADRES + "/#firma", "name": FIRMA, "url": ADRES + "/"}


def wiek_od_do(gra: dict) -> tuple[int, int] | None:
    liczby = re.findall(r"\d+", gra.get("wiek") or "")
    return (int(liczby[0]), int(liczby[-1])) if liczby else None


def seo(gra: dict) -> dict:
    """Tytuł, opis i kategoria dla wyszukiwarek. Pole "seo" w danych gry nadpisuje domyślne."""
    s = gra.get("seo") or {}
    return {
        "tytul": s.get("tytul") or f"{pelna_nazwa(gra)} · gra dla dzieci",
        "opis": s.get("opis") or gra["opis_krotki"]["pl"],
        "kategoria": s.get("kategoria") or "GameApplication",
        "tematy": s.get("tematy") or [],
    }


def dane_gry(gra: dict) -> list[dict]:
    url = adres(f"gry/{gra['slug']}/")
    s = seo(gra)
    aplikacja = {
        "@context": "https://schema.org",
        "@type": ["SoftwareApplication", "VideoGame"],
        "@id": url + "#gra",
        "name": pelna_nazwa(gra),
        "alternateName": gra.get("nazwa_en") or gra["nazwa"],
        "url": url,
        "description": s["opis"],
        "applicationCategory": s["kategoria"],
        "operatingSystem": "Android",
        "inLanguage": "pl",
        "isFamilyFriendly": True,
        "publisher": wydawca(),
        "author": wydawca(),
    }
    if gra.get("okladka"):
        aplikacja["image"] = adres(gra["okladka"])
    if gra.get("zrzuty"):
        aplikacja["screenshot"] = [adres(z["plik"]) for z in gra["zrzuty"]]
    wiek = wiek_od_do(gra)
    if wiek:
        aplikacja["audience"] = {"@type": "PeopleAudience",
                                 "suggestedMinAge": wiek[0], "suggestedMaxAge": wiek[1]}
        aplikacja["typicalAgeRange"] = f"{wiek[0]}-{wiek[1]}"
    if s["tematy"]:
        aplikacja["keywords"] = ", ".join(s["tematy"])
    if gra["wydania"]:
        aplikacja["softwareVersion"] = gra["wydania"][0]["wersja"]
    sklep = link_sklepu(gra, "schema")
    if sklep:
        aplikacja["installUrl"] = sklep
    okruszki = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Senne gry Artura", "item": ADRES + "/"},
            {"@type": "ListItem", "position": 2, "name": pelna_nazwa(gra), "item": url},
        ],
    }
    return [aplikacja, okruszki]


def meta_udostepniania(url: str, tytul: str, opis: str, obraz: str) -> str:
    """Adres kanoniczny i podgląd linku (Facebook, Messenger, WhatsApp, X)."""
    wiersze = [
        f'<link rel="canonical" href="{e(url)}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="pl_PL">',
        '<meta property="og:site_name" content="Senne gry Artura">',
        f'<meta property="og:url" content="{e(url)}">',
        f'<meta property="og:title" content="{e(tytul)}">',
        f'<meta property="og:description" content="{e(opis)}">',
    ]
    if obraz:
        wiersze += [f'<meta property="og:image" content="{e(obraz)}">',
                    f'<meta property="og:image:alt" content="{e(tytul)}">',
                    '<meta name="twitter:card" content="summary_large_image">']
    return "\n".join(wiersze)


def mapa_strony(gry: list[dict], porady: list[dict] | None = None) -> str:
    wpisy = [(adres("" if n == "index.html" else n), None, "1.0" if n == "index.html" else "0.3")
             for n in STRONY_RECZNE if (KORZEN / n).exists()]
    for g in gry:
        data = g["wydania"][0]["data"] if g["wydania"] else None
        wpisy.append((adres(f"gry/{g['slug']}/"), data, "0.9"))
    if porady:
        wpisy.append((adres("ortografia/"), None, "0.8"))
        wpisy += [(adres(f"ortografia/{p['slug']}/"), None, "0.8") for p in porady]
    linie = []
    for url, data, pr in wpisy:
        mod = f"<lastmod>{data}</lastmod>" if data else ""
        linie.append(f"  <url><loc>{html.escape(url)}</loc>{mod}<priority>{pr}</priority></url>")
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "\n".join(linie) + "\n</urlset>\n")


def robots() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {ADRES}/sitemap.xml\n"


# ---------- HTML ----------

def rok(gra: dict) -> int:
    """Rok w stopce z danych, nie z zegara, żeby wynik był powtarzalny."""
    return max([2026] + [int(w["data"][:4]) for w in gra["wydania"]])


def pelna_nazwa(gra: dict, jezyk: str = "pl") -> str:
    pod = (gra.get("podtytul") or {}).get(jezyk)
    return f"{gra['nazwa']}: {pod}" if pod else gra["nazwa"]


def znaczek_wersji(gra: dict) -> str:
    n = gra["wydania"][0] if gra["wydania"] else None
    if not n:
        return ""
    return (f'<p class="cichy">Wersja {e(n["wersja"])} · {e(SCIEZKI[n["sciezka"]][0])} · '
            f'{e(data_pl(n["data"]))}</p>')


def przycisk_sklepu(gra: dict, zrodlo: str) -> str:
    sklep = link_sklepu(gra, zrodlo)
    if sklep:
        return f'<a class="przycisk" href="{e(sklep)}">Pobierz z Google Play</a>'
    return '<span class="wkrotce">Wkrótce w Google Play. Gra jest teraz w testach.</span>'


def karta_gry(gra: dict) -> str:
    s = e(gra["slug"])
    obraz = ""
    if gra.get("okladka"):
        obraz = (f'<a href="gry/{s}/"><img src="{e(gra["okladka"])}" '
                 f'alt="{e(pelna_nazwa(gra))}: ekran gry dla dzieci" width="1280" height="720"></a>')
    znaczki = "".join(f"<li>{e(t)}</li>" for t in
                      ([f"dla dzieci {gra['wiek']}"] if gra.get("wiek") else [])
                      + gra.get("znaczki", ["bez reklam", "offline", "we dwoje"]))
    linki = [f'<a href="gry/{s}/">Więcej o grze</a>']
    if gra.get("polityka"):
        linki.append(f'<a href="{e(gra["polityka"])}">Polityka prywatności</a>')
    return (
        f'  <article class="gra">\n'
        f'    {obraz}\n'
        f'    <div class="gra-opis jasne">\n'
        f'      <h3><a href="gry/{s}/">{e(pelna_nazwa(gra))}</a></h3>\n'
        f'      <p>{e(gra["opis_krotki"]["pl"])}</p>\n'
        f'      <ul class="znaczki">{znaczki}</ul>\n'
        f'      <div class="przyciski">{przycisk_sklepu(gra, "karta")}</div>\n'
        f'      {znaczek_wersji(gra)}\n'
        f'      <p>{" · ".join(linki)}</p>\n'
        f'    </div>\n'
        f'  </article>'
    )


def lista_notatek(notatki: list[str]) -> str:
    return '<ul class="lista">' + "".join(f"<li>{e(n)}</li>" for n in notatki) + "</ul>"


GWIAZDY = "".join(
    f'<span style="left:{(i * 37) % 100}%;top:{(i * 53) % 70}%;animation-delay:{(i % 7) * 0.6:.1f}s"></span>'
    for i in range(1, 28))

LOGO_SVG = ('<svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">'
            '<circle cx="16" cy="16" r="15" fill="#3d2a7a"/>'
            '<path d="M21 6a10 10 0 1 0 5 15A8 8 0 0 1 21 6z" fill="#ffe08a"/></svg>')


def pasek(g: str, en: bool = True) -> str:
    return (f'<header class="pasek"><div class="wrap">'
            f'<a class="logo" href="{g}index.html">{LOGO_SVG}Senne gry Artura</a>'
            f'<nav class="menu"><a href="{g}index.html#gry">Gry</a><a href="{g}ortografia/">Zasady ortografii</a>'
            f'<a href="{g}index.html#rodzice">Dla rodziców</a>'
            f'<a href="{g}index.html#dzieci">Dla dzieci</a><a href="{g}index.html#kontakt">Kontakt</a>'
            + ('<a href="#en">English</a>' if en else "") + '</nav></div></header>')


def stopka(rok_: int, g: str, polityka: str = "polityka-prywatnosci.html") -> str:
    return (f'<footer><div class="wrap"><span>© {rok_} {FIRMA}</span>'
            f'<span><a href="{g}{e(polityka)}">Polityka prywatności</a> · '
            f'<a href="{g}feed.xml">Wydania (RSS)</a></span></div></footer>')


def strona_gry(gra: dict) -> str:
    g = "../../"
    czesci = []
    okladka = ""
    if gra.get("okladka"):
        okladka = (f'<img src="{g}{e(gra["okladka"])}" alt="{e(pelna_nazwa(gra))}: ekran gry dla dzieci" '
                   f'width="1280" height="720">')
    znaczki = "".join(f"<li>{e(t)}</li>" for t in
                      ([f"dla dzieci {gra['wiek']}"] if gra.get("wiek") else [])
                      + ["bez reklam", "bez internetu", "bez zbierania danych"])
    czesci.append(
        f'<section class="niebo"><div class="gwiazdy" aria-hidden="true">{GWIAZDY}</div>'
        f'<div class="ksiezyc" aria-hidden="true"></div>'
        f'<div class="wrap niebo-tresc"><div>'
        f'<h1>{e(pelna_nazwa(gra))}</h1>'
        f'<p class="lead">{e(gra["opis_krotki"]["pl"])}</p>'
        f'<ul class="znaczki">{znaczki}</ul>'
        f'<div class="przyciski">{przycisk_sklepu(gra, "strona-gry")}</div>'
        f'</div><div>{okladka}</div></div></section>')

    tresc = "".join(f"<p>{e(a)}</p>" for a in gra["opis"]["pl"])
    czesci.append(f'<section><div class="wrap waski"><h2>O grze</h2>{tresc}</div></section>')

    if gra.get("cechy"):
        kafle = "".join(
            f'<div class="kafel"><div class="ikona {e(c.get("kolor", ""))}" aria-hidden="true">{e(c["ikona"])}</div>'
            f'<h3>{e(c["tytul"])}</h3><p>{e(c["opis"])}</p></div>' for c in gra["cechy"])
        czesci.append(f'<section><div class="wrap"><h2>Co jest w grze</h2><div class="kafelki">{kafle}</div></div></section>')

    if gra.get("zrzuty"):
        figury = "".join(
            f'<figure><img src="{g}{e(z["plik"])}" alt="{e(z["opis"]["pl"])}" '
            f'width="{z.get("szerokosc", 1280)}" height="{z.get("wysokosc", 720)}" loading="lazy">'
            f'<figcaption>{e(z["opis"]["pl"])}</figcaption></figure>' for z in gra["zrzuty"])
        czesci.append(f'<section><div class="wrap"><h2>Tak to wygląda</h2><div class="zrzuty">{figury}</div></div></section>')

    if gra.get("dla_rodzicow"):
        polityka = (f'<p><a href="{g}{e(gra["polityka"])}">Polityka prywatności gry {e(gra["nazwa"])}</a></p>'
                    if gra.get("polityka") else "")
        czesci.append(f'<section id="rodzice"><div class="wrap waski"><h2>Dla rodziców</h2>'
                      f'{lista_notatek(gra["dla_rodzicow"])}{polityka}</div></section>')

    if gra["wydania"]:
        wyd = []
        for i, w in enumerate(gra["wydania"]):
            naglowek = (f'Wersja {e(w["wersja"])} <span class="cichy">({e(data_pl(w["data"]))}, '
                        f'{e(SCIEZKI[w["sciezka"]][0])})</span>')
            kotwica = f'v{e(w["wersja"])}-{w["kod"]}'
            if i == 0:
                wyd.append(f'<h3 id="{kotwica}">{naglowek}</h3>{lista_notatek(w["notatki"]["pl"])}')
            else:
                wyd.append(f'<details id="{kotwica}"><summary>{naglowek}</summary>{lista_notatek(w["notatki"]["pl"])}</details>')
        czesci.append(f'<section><div class="wrap waski"><h2>Co nowego</h2>{"".join(wyd)}</div></section>')

    # English
    n = gra["wydania"][0] if gra["wydania"] else None
    en = [f'<h2>{e(gra.get("nazwa_en") or gra["nazwa"])} (English)</h2>']
    en += [f"<p>{e(a)}</p>" for a in gra["opis"]["en"]]
    if n:
        en.append(f'<p class="cichy">Latest version: {e(n["wersja"])} · {e(SCIEZKI[n["sciezka"]][1])} · {e(n["data"])}</p>')
    sklep = link_sklepu(gra, "strona-gry-en")
    if sklep:
        en.append(f'<p><a class="przycisk" href="{e(sklep)}">Get it on Google Play</a></p>')
    czesci.append(f'<section id="en"><div class="wrap waski">{"".join(en)}</div></section>')

    tresc = "\n".join(czesci)
    obraz_og = adres(gra["okladka"]) if gra.get("okladka") else ""
    s = seo(gra)
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(s["tytul"])}</title>
<meta name="description" content="{e(s["opis"])}">
{meta_udostepniania(adres(f"gry/{gra['slug']}/"), pelna_nazwa(gra), s["opis"], obraz_og)}
{jsonld(dane_gry(gra))}
<link rel="icon" href="{g}ikona.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="Wydania gier" href="{g}feed.xml">
<link rel="stylesheet" href="{g}styl.css">
</head>
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z dane/gry/{e(gra["slug"])}.json. Nie edytuj ręcznie. -->
{pasek(g)}
<main>
{tresc}
</main>
{stopka(rok(gra), g, gra.get("polityka") or "polityka-prywatnosci.html")}
{statystyki()}
</body>
</html>
"""


def podmien_index(gry: list[dict]) -> None:
    plik = KORZEN / "index.html"
    tekst = plik.read_text(encoding="utf-8")
    if ZNACZNIK_START not in tekst or ZNACZNIK_KONIEC not in tekst:
        sys.exit("index.html: brak znaczników <!-- gry:start --> / <!-- gry:koniec -->")
    przed, reszta = tekst.split(ZNACZNIK_START, 1)
    _, po = reszta.split(ZNACZNIK_KONIEC, 1)
    karty = "\n".join(karta_gry(g) for g in gry)
    plik.write_text(f"{przed}{ZNACZNIK_START}\n{karty}\n  {ZNACZNIK_KONIEC}{po}", encoding="utf-8")


# ---------- zasady ortografii ----------

def wczytaj_porady() -> list[dict]:
    porady = []
    for plik in sorted(DANE_ORTO.glob("*.json")):
        p = json.loads(plik.read_text(encoding="utf-8"))
        if p.get("slug") != plik.stem:
            sys.exit(f"{plik}: pole slug musi być równe nazwie pliku ({plik.stem})")
        porady.append(p)
    porady.sort(key=lambda p: (p.get("kolejnosc", 999), p["slug"]))
    return porady


WYRAZ = re.compile(r"^([^\[\]]*)\[([^\[\]]+)\]([^\[\]]*)$")


def rozbij(zapis: str) -> tuple[str, str, str]:
    """"st[ó]ł" -> ("st", "ó", "ł"). Ten sam zapis co w grze Ortopotwory."""
    m = WYRAZ.match(zapis)
    if not m:
        sys.exit(f"Zły zapis wyrazu: {zapis!r} (oczekiwano np. st[ó]ł)")
    return m.group(1), m.group(2), m.group(3)


def wyraz_html(zapis: str) -> str:
    """Wyraz z wyróżnioną literą. Zawsze poprawna pisownia, nigdy wersja z błędem."""
    przed, litera, po = rozbij(zapis)
    return f'{e(przed)}<b class="litera">{e(litera)}</b>{e(po)}'


def wyraz_tekst(zapis: str) -> str:
    return "".join(rozbij(zapis))


def luka_html(zapis: str) -> str:
    przed, litera, po = rozbij(zapis)
    return f'{e(przed)}<span class="luka" aria-label="brakująca litera">{"_" * len(litera)}</span>{e(po)}'


def przyklad_html(p: str) -> str:
    wyraz, _, bo = p.partition("|")
    return f"<li>{wyraz_html(wyraz)}" + (f' <span class="cichy">bo {e(bo)}</span>' if bo else "") + "</li>"


def strona_porady(p: dict, porady: list[dict], gra: dict | None) -> str:
    g = "../../"
    url = adres(f"ortografia/{p['slug']}/")
    czesci = []
    skrot = "".join(f"<li>{punkt}</li>" for punkt in p["w_skrocie"])  # punkty mają celowo <b>
    czesci.append(
        f'<section class="porada-gora"><div class="wrap waski">'
        f'<p class="okruszki"><a href="{g}index.html">Senne gry Artura</a> › <a href="../">Zasady ortografii</a></p>'
        f'<h1>{e(p["tytul"])}</h1><p class="lead">{e(p["wstep"])}</p>'
        f'<div class="ramka"><h2>W skrócie</h2><ul class="lista">{skrot}</ul></div>'
        f'</div></section>')

    reg = []
    for r in p["reguly"]:
        wyj = f'<p class="uwaga">{e(r["wyjatki"])}</p>' if r.get("wyjatki") else ""
        przyk = "".join(przyklad_html(x) for x in r["przyklady"])
        reg.append(f'<h3>{e(r["tytul"])}</h3><p>{e(r["tekst"])}</p><ul class="wyrazy">{przyk}</ul>{wyj}')
    czesci.append(f'<section><div class="wrap waski"><h2>Zasady pisowni {e(p["litery"])}</h2>{"".join(reg)}</div></section>')

    z = p.get("do_zapamietania")
    if z:
        wyrazy = "".join(f"<li>{wyraz_html(w)}</li>" for w in z["wyrazy"])
        czesci.append(f'<section><div class="wrap waski"><h2>{e(z["tytul"])}</h2><p>{e(z["tekst"])}</p>'
                      f'<ul class="wyrazy">{wyrazy}</ul></div></section>')

    if p.get("cwiczenie"):
        luki = "".join(f"<li>{luka_html(w)}</li>" for w in p["cwiczenie"])
        odp = "".join(f"<li>{wyraz_html(w)}</li>" for w in p["cwiczenie"])
        czesci.append(
            f'<section><div class="wrap waski"><h2>Ćwiczenie: wpisz {e(p["litery"])}</h2>'
            f'<p>Przepisz wyrazy do zeszytu i wpisz brakujące litery. Potem sprawdź odpowiedzi.</p>'
            f'<ol class="wyrazy cwiczenie">{luki}</ol>'
            f'<details><summary>Pokaż odpowiedzi</summary><ol class="wyrazy">{odp}</ol></details>'
            f'</div></section>')

    if p.get("dla_rodzica"):
        czesci.append(f'<section><div class="wrap waski"><h2>Jak ćwiczyć w domu</h2>{lista_notatek(p["dla_rodzica"])}</div></section>')

    if gra:
        czesci.append(
            f'<section><div class="wrap waski"><div class="kontakt">'
            f'<h2>Poćwicz z Ortopotworami</h2>'
            f'<p>{e(gra["opis_krotki"]["pl"])} Wyrazy z tej strony wracają w grze w powtórkach po 1, 3, 7, 14 i 30 dniach.</p>'
            f'<div class="przyciski"><a class="przycisk" href="{g}gry/{e(gra["slug"])}/">Poznaj grę Ortopotwory</a></div>'
            f'</div></div></section>')

    if p.get("pytania"):
        pyt = "".join(f'<details><summary>{e(q["p"])}</summary><p>{e(q["o"])}</p></details>' for q in p["pytania"])
        czesci.append(f'<section><div class="wrap waski"><h2>Częste pytania</h2>{pyt}</div></section>')

    inne = [x for x in porady if x["slug"] != p["slug"]]
    if inne:
        linki = "".join(f'<li><a href="../{e(x["slug"])}/">{e(x["tytul"])}</a></li>' for x in inne)
        czesci.append(f'<section><div class="wrap waski"><h2>Inne zasady ortografii</h2><ul class="lista">{linki}</ul></div></section>')

    dane = [
        {
            "@context": "https://schema.org",
            "@type": ["Article", "LearningResource"],
            "@id": url + "#porada",
            "headline": p["tytul"],
            "description": p["seo"]["opis"],
            "url": url,
            "inLanguage": "pl",
            "learningResourceType": "zasady i ćwiczenie",
            "educationalLevel": "szkoła podstawowa, klasy 1–4",
            "teaches": f"pisownia {p['litery']}",
            "isAccessibleForFree": True,
            "author": wydawca(),
            "publisher": wydawca(),
        },
        {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q["p"],
                            "acceptedAnswer": {"@type": "Answer", "text": q["o"]}} for q in p.get("pytania", [])],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Senne gry Artura", "item": ADRES + "/"},
                {"@type": "ListItem", "position": 2, "name": "Zasady ortografii", "item": adres("ortografia/")},
                {"@type": "ListItem", "position": 3, "name": p["tytul"], "item": url},
            ],
        },
    ]
    if not p.get("pytania"):
        dane.pop(1)
    return strona_szkielet(g, url, p["seo"]["tytul"], p["seo"]["opis"], p["tytul"], dane,
                           "\n".join(czesci), f"dane/ortografia/{p['slug']}.json")


def strona_ortografii(porady: list[dict]) -> str:
    g = "../"
    url = adres("ortografia/")
    karty = "".join(
        f'<div class="kafel"><div class="ikona {"frs"[i % 3]}" aria-hidden="true">{e(p["litery"])}</div>'
        f'<h3><a href="{e(p["slug"])}/">{e(p["tytul"])}</a></h3><p>{e(p["opis_krotki"])}</p></div>'
        for i, p in enumerate(porady))
    tresc = (
        f'<section class="porada-gora"><div class="wrap waski">'
        f'<p class="okruszki"><a href="{g}index.html">Senne gry Artura</a></p>'
        f'<h1>Zasady ortografii dla dzieci</h1>'
        f'<p class="lead">Proste zasady pisowni ó i u, rz i ż oraz ch i h, z przykładami i ćwiczeniami z odpowiedziami. '
        f'Dla dzieci w klasach 1–4 i rodziców, którzy pomagają w lekcjach.</p></div></section>'
        f'<section><div class="wrap"><div class="kafelki">{karty}</div></div></section>'
        f'<section><div class="wrap waski"><h2>Jak uczyć ortografii, żeby została w głowie</h2>'
        + lista_notatek([
            "Szukajcie rodziny wyrazu: stół, bo stoły; dobrze, bo dobry. To jedna sztuczka do wielu reguł.",
            "Pokazuj tylko poprawny zapis. Puste miejsce na literę działa lepiej niż poprawianie błędów.",
            "Ćwiczcie krótko i często, a trudne wyrazy powtarzajcie po kilku dniach.",
            "Wyjątki łączcie w zabawne zdania albo historyjki, wtedy łatwiej je zapamiętać.",
        ])
        + f'<p>Te same zasady ćwiczy gra <a href="{g}gry/ortopotwory/">Ortopotwory: Detektywi ortografii</a>.</p>'
        f'</div></section>')
    dane = [
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "@id": url,
            "name": "Zasady ortografii dla dzieci",
            "url": url,
            "inLanguage": "pl",
            "publisher": wydawca(),
            "hasPart": [{"@type": "Article", "headline": p["tytul"], "url": adres(f"ortografia/{p['slug']}/")}
                        for p in porady],
        },
        {
            "@context": "https://schema.org",
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Senne gry Artura", "item": ADRES + "/"},
                {"@type": "ListItem", "position": 2, "name": "Zasady ortografii", "item": url},
            ],
        },
    ]
    return strona_szkielet(g, url, "Zasady ortografii dla dzieci: ó/u, rz/ż, ch/h z ćwiczeniami",
                           "Zasady pisowni ó i u, rz i ż, ch i h dla dzieci z klas 1–4: proste reguły, przykłady, "
                           "wyjątki do zapamiętania i ćwiczenia z odpowiedziami.",
                           "Zasady ortografii dla dzieci", dane, tresc, "dane/ortografia/*.json")


def strona_szkielet(g: str, url: str, tytul: str, opis: str, tytul_og: str, dane: list[dict],
                    tresc: str, zrodlo: str) -> str:
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(tytul)}</title>
<meta name="description" content="{e(opis)}">
{meta_udostepniania(url, tytul_og, opis, adres("img/gry/ortopotwory/okladka.jpg"))}
{jsonld(dane)}
<link rel="icon" href="{g}ikona.svg" type="image/svg+xml">
<link rel="stylesheet" href="{g}styl.css">
</head>
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(zrodlo)}. Nie edytuj ręcznie. -->
{pasek(g, en=False)}
<main>
{tresc}
</main>
{stopka(2026, g)}
{statystyki()}
</body>
</html>
"""


# ---------- dane dla automatów ----------

def wpisy_wydan(gry: list[dict]) -> list[tuple[dict, dict]]:
    wpisy = [(g, w) for g in gry for w in g["wydania"]]
    wpisy.sort(key=lambda gw: (gw[1]["data"], gw[1]["kod"]), reverse=True)
    return wpisy


def id_wydania(gra: dict, w: dict) -> str:
    return f"{gra['slug']}-{w['wersja']}-{w['kod']}"


def api_gry(gry: list[dict]) -> dict:
    wynik = []
    for g in gry:
        n = g["wydania"][0] if g["wydania"] else None
        wynik.append({
            "slug": g["slug"],
            "nazwa": g["nazwa"],
            "podtytul": g.get("podtytul"),
            "nazwa_en": g.get("nazwa_en"),
            "pakiet": g.get("pakiet"),
            "strona": adres(f"gry/{g['slug']}/"),
            "google_play": link_sklepu(g, "api"),
            "polityka_prywatnosci": adres(g["polityka"]) if g.get("polityka") else None,
            "opis_krotki": g["opis_krotki"],
            "opis": g["opis"],
            "okladka": adres(g["okladka"]) if g.get("okladka") else None,
            "zrzuty": [{"url": adres(z["plik"]), "opis": z["opis"]} for z in g.get("zrzuty", [])],
            "najnowsze_wydanie": None if n is None else {
                "id": id_wydania(g, n), "wersja": n["wersja"], "kod": n["kod"],
                "data": n["data"], "sciezka": n["sciezka"], "notatki": n["notatki"],
            },
        })
    return {"wydawca": FIRMA, "strona": ADRES + "/", "gry": wynik}


def json_feed(gry: list[dict]) -> dict:
    items = []
    for g, w in wpisy_wydan(gry):
        url = adres(f"gry/{g['slug']}/#v{w['wersja']}-{w['kod']}")
        items.append({
            "id": id_wydania(g, w),
            "url": url,
            "title": f"{g['nazwa']} {w['wersja']}",
            "content_text": "\n".join(f"• {n}" for n in w["notatki"]["pl"]),
            "date_published": f"{w['data']}T12:00:00+00:00",
            "image": adres(g["okladka"]) if g.get("okladka") else None,
            "tags": [g["slug"], w["sciezka"]],
            "_wydanie": {
                "gra": g["slug"], "wersja": w["wersja"], "kod": w["kod"], "sciezka": w["sciezka"],
                "publiczne": w["sciezka"] == "production",
                "notatki": w["notatki"],
                "zrzuty": [adres(z["plik"]) for z in g.get("zrzuty", [])],
                "google_play": link_sklepu(g, "wydania"),
            },
        })
    return {
        "version": "https://jsonfeed.org/version/1.1",
        "title": f"{FIRMA}: wydania gier",
        "home_page_url": ADRES + "/",
        "feed_url": adres("api/wydania.json"),
        "language": "pl",
        "items": items,
    }


def rss(gry: list[dict]) -> str:
    def x(t: str) -> str:
        return html.escape(t, quote=False)

    pozycje = []
    for g, w in wpisy_wydan(gry):
        data = dt.datetime.fromisoformat(f"{w['data']}T12:00:00+00:00")
        url = adres(f"gry/{g['slug']}/#v{w['wersja']}-{w['kod']}")
        opis = "\n".join(f"• {n}" for n in w["notatki"]["pl"])
        pozycje.append(
            "    <item>\n"
            f"      <title>{x(g['nazwa'])} {x(w['wersja'])}</title>\n"
            f"      <link>{x(url)}</link>\n"
            f"      <guid isPermaLink=\"false\">{x(id_wydania(g, w))}</guid>\n"
            f"      <pubDate>{format_datetime(data)}</pubDate>\n"
            f"      <category>{x(g['slug'])}</category>\n"
            f"      <description>{x(opis)}</description>\n"
            "    </item>")
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<rss version="2.0">\n'
        "  <channel>\n"
        f"    <title>{x(FIRMA)}: wydania gier</title>\n"
        f"    <link>{ADRES}/</link>\n"
        "    <description>Nowe wersje naszych gier dla dzieci</description>\n"
        "    <language>pl</language>\n"
        + "\n".join(pozycje) + ("\n" if pozycje else "")
        + "  </channel>\n</rss>\n"
    )


# ---------- polecenia ----------

def statystyki() -> str:
    """Blok ze skryptem Cloudflare Web Analytics albo pusty blok, gdy nie ma tokenu."""
    plik = KORZEN / "dane" / "statystyki.json"
    token = json.loads(plik.read_text(encoding="utf-8")).get("cloudflare_token", "") if plik.exists() else ""
    if token and not re.fullmatch(r"[0-9a-f]{32}", token):
        sys.exit("dane/statystyki.json: cloudflare_token to 32 znaki 0-9a-f")
    skrypt = ("<script defer src=\"https://static.cloudflareinsights.com/beacon.min.js\" "
              f"data-cf-beacon='{{\"token\": \"{token}\"}}'></script>\n" if token else "")
    return f"{STAT_START}\n{skrypt}{STAT_KONIEC}"


def wstaw_statystyki(tekst: str, blok: str) -> str:
    if STAT_START in tekst:
        przed, reszta = tekst.split(STAT_START, 1)
        return przed + blok + reszta.split(STAT_KONIEC, 1)[1]
    return tekst.replace("</body>", f"{blok}\n</body>", 1)


def zbuduj() -> None:
    gry = wczytaj_gry()
    for g in gry:
        for w in g["wydania"]:
            if w["sciezka"] not in SCIEZKI:
                sys.exit(f"{g['slug']} {w['wersja']}: nieznana ścieżka {w['sciezka']}")
        for z in g.get("zrzuty", []):
            if not (KORZEN / z["plik"]).is_file():
                sys.exit(f"{g['slug']}: brak pliku zrzutu {z['plik']}")
        katalog = KORZEN / "gry" / g["slug"]
        katalog.mkdir(parents=True, exist_ok=True)
        (katalog / "index.html").write_text(strona_gry(g), encoding="utf-8")
    podmien_index(gry)
    porady = wczytaj_porady()
    if porady:
        orto = KORZEN / "ortografia"
        gra_orto = next((x for x in gry if x["slug"] == "ortopotwory"), None)
        for p in porady:
            (orto / p["slug"]).mkdir(parents=True, exist_ok=True)
            (orto / p["slug"] / "index.html").write_text(strona_porady(p, porady, gra_orto), encoding="utf-8")
        (orto / "index.html").write_text(strona_ortografii(porady), encoding="utf-8")
    blok = statystyki()
    for nazwa in STRONY_RECZNE:
        plik = KORZEN / nazwa
        if plik.exists():
            plik.write_text(wstaw_statystyki(plik.read_text(encoding="utf-8"), blok), encoding="utf-8")
    (KORZEN / "api").mkdir(exist_ok=True)
    (KORZEN / "api" / "gry.json").write_text(
        json.dumps(api_gry(gry), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KORZEN / "api" / "wydania.json").write_text(
        json.dumps(json_feed(gry), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KORZEN / "feed.xml").write_text(rss(gry), encoding="utf-8")
    (KORZEN / "sitemap.xml").write_text(mapa_strony(gry, porady), encoding="utf-8")
    (KORZEN / "robots.txt").write_text(robots(), encoding="utf-8")
    print(f"Zbudowano strony dla gier: {', '.join(g['slug'] for g in gry)}")


def czytaj_notatki(sciezka: str | None) -> list[str]:
    if not sciezka:
        return []
    linie = Path(sciezka).read_text(encoding="utf-8").splitlines()
    return [l.strip().lstrip("-•*").strip() for l in linie
            if l.strip() and not l.strip().startswith("#")]


def wydanie(a: argparse.Namespace) -> None:
    plik = DANE / f"{a.gra}.json"
    if not plik.is_file():
        sys.exit(f"Brak {plik.relative_to(KORZEN)}. Najpierw: strona.py nowa-gra --gra {a.gra} --nazwa ...")
    gra = json.loads(plik.read_text(encoding="utf-8"))
    pl = czytaj_notatki(a.notatki_pl) or ["Poprawki i ulepszenia."]
    en = czytaj_notatki(a.notatki_en) or ["Fixes and improvements."]
    poprzednie = [w for w in gra.get("wydania", []) if w["kod"] != a.kod]
    if poprzednie and max(poprzednie, key=lambda w: w["kod"])["notatki"]["pl"] == pl:
        print("::warning::Notatki „co nowego” są takie same jak w poprzedniej wersji. Zaktualizuj sklep/co-nowego/ w repozytorium gry.")
    nowe = {"wersja": a.wersja, "kod": a.kod, "data": a.data or dt.date.today().isoformat(),
            "sciezka": a.sciezka, "notatki": {"pl": pl, "en": en}}
    # Ponowne uruchomienie tego samego wydania nadpisuje wpis zamiast dublować.
    gra["wydania"] = [w for w in gra.get("wydania", []) if w["kod"] != a.kod] + [nowe]
    gra["wydania"].sort(key=lambda w: w["kod"], reverse=True)

    if a.zrzuty:
        zrodlo = Path(a.zrzuty)
        pliki = sorted(zrodlo.glob("*.png")) + sorted(zrodlo.glob("*.jpg"))
        if pliki:
            cel = KORZEN / "img" / "gry" / a.gra
            cel.mkdir(parents=True, exist_ok=True)
            stare = {z["plik"]: z for z in gra.get("zrzuty", [])}
            zrzuty = []
            for p in pliki:
                shutil.copyfile(p, cel / p.name)
                rel = f"img/gry/{a.gra}/{p.name}"
                podpis = re.sub(r"^\d+[-_]", "", p.stem).replace("-", " ").replace("_", " ").capitalize()
                zrzuty.append(stare.get(rel, {"plik": rel, "opis": {"pl": podpis, "en": podpis}}))
            gra["zrzuty"] = zrzuty
            if not gra.get("okladka"):
                gra["okladka"] = zrzuty[0]["plik"]
    zapisz_gre(gra)
    print(f"Dopisano wydanie {a.gra} {a.wersja} ({a.kod}, {a.sciezka})")
    zbuduj()


def nowa_gra(a: argparse.Namespace) -> None:
    if not SLUG.match(a.gra):
        sys.exit("Identyfikator gry: małe litery, cyfry i myślniki, np. moja-gra")
    plik = DANE / f"{a.gra}.json"
    if plik.exists():
        sys.exit(f"{plik.relative_to(KORZEN)} już istnieje")
    zapisz_gre({
        "slug": a.gra, "kolejnosc": 100, "nazwa": a.nazwa, "nazwa_en": a.nazwa,
        "pakiet": a.pakiet, "okladka": None, "polityka": None,
        "opis_krotki": {"pl": "Opis wkrótce.", "en": "Coming soon."},
        "opis": {"pl": ["Opis wkrótce."], "en": ["Coming soon."]},
        "zrzuty": [], "wydania": [],
    })
    print(f"Utworzono {plik.relative_to(KORZEN)}. Uzupełnij opisy i uruchom: strona.py zbuduj")
    zbuduj()


def main() -> None:
    p = argparse.ArgumentParser(description="Generator strony arturbyrski.pl")
    sub = p.add_subparsers(dest="polecenie", required=True)
    sub.add_parser("zbuduj", help="wygeneruj strony i feedy z dane/gry/*.json")
    w = sub.add_parser("wydanie", help="dopisz wydanie gry i przebuduj stronę")
    w.add_argument("--gra", required=True)
    w.add_argument("--wersja", required=True)
    w.add_argument("--kod", required=True, type=int)
    w.add_argument("--sciezka", required=True, choices=sorted(SCIEZKI))
    w.add_argument("--data")
    w.add_argument("--notatki-pl")
    w.add_argument("--notatki-en")
    w.add_argument("--zrzuty", help="katalog z plikami PNG/JPG (zastępuje listę zrzutów)")
    n = sub.add_parser("nowa-gra", help="dodaj nową grę do strony")
    n.add_argument("--gra", required=True)
    n.add_argument("--nazwa", required=True)
    n.add_argument("--pakiet")
    a = p.parse_args()
    if a.polecenie == "zbuduj":
        zbuduj()
    elif a.polecenie == "wydanie":
        wydanie(a)
    else:
        nowa_gra(a)


if __name__ == "__main__":
    main()

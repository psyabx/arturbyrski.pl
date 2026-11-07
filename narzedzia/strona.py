#!/usr/bin/env python3
"""Generator strony arturbyrski.pl z danych gier (bez zewnętrznych bibliotek).

Źródło prawdy: dane/gry/<slug>.json (jedna gra = jeden plik).
Wynik (commitowany, bo GitHub Pages serwuje gałąź main):
  - index.html            sekcja między <!-- gry:start --> i <!-- gry:koniec -->
  - gry/<slug>/index.html strona gry z wersją, zrzutami i historią zmian
  - api/gry.json          wszystkie gry i ich najnowsze wersje (dla automatów, np. influencera)
  - api/wydania.json      JSON Feed 1.1 z wydaniami, od najnowszego
  - feed.xml              RSS 2.0 z wydaniami

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
ADRES = "https://arturbyrski.pl"
FIRMA = "Artur Byrski Link Technologies"
ZNACZNIK_START = "<!-- gry:start -->"
ZNACZNIK_KONIEC = "<!-- gry:koniec -->"
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


def link_sklepu(gra: dict) -> str | None:
    """Link do Google Play pokazujemy dopiero, gdy jest wydanie produkcyjne."""
    if gra.get("pakiet") and any(w["sciezka"] == "production" for w in gra["wydania"]):
        return f"https://play.google.com/store/apps/details?id={gra['pakiet']}"
    return None


def adres(sciezka: str) -> str:
    return f"{ADRES}/{sciezka.lstrip('/')}"


def data_pl(iso: str) -> str:
    miesiace = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
                "sierpnia", "września", "października", "listopada", "grudnia"]
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {miesiace[d.month - 1]} {d.year}"


# ---------- HTML ----------

def rok(gra: dict) -> int:
    """Rok w stopce z danych, nie z zegara, żeby wynik był powtarzalny."""
    return max([2026] + [int(w["data"][:4]) for w in gra["wydania"]])


def karta_gry(gra: dict) -> str:
    najnowsze = gra["wydania"][0] if gra["wydania"] else None
    wersja = ""
    if najnowsze:
        wersja = (f'<p class="cichy">Wersja {e(najnowsze["wersja"])} · '
                  f'{e(SCIEZKI[najnowsze["sciezka"]][0])} · {e(data_pl(najnowsze["data"]))}</p>')
    obraz = ""
    if gra.get("okladka"):
        obraz = (f'<a href="gry/{e(gra["slug"])}/"><img src="{e(gra["okladka"])}" '
                 f'alt="Ekran gry {e(gra["nazwa"])}" width="1280" height="720"></a>')
    linki = [f'<a href="gry/{e(gra["slug"])}/">Więcej o grze</a>']
    sklep = link_sklepu(gra)
    if sklep:
        linki.append(f'<a href="{e(sklep)}">Google Play</a>')
    if gra.get("polityka"):
        linki.append(f'<a href="{e(gra["polityka"])}">Polityka prywatności</a>')
    return (
        f'  <div class="karta">\n'
        f'    {obraz}\n'
        f'    <h3><a href="gry/{e(gra["slug"])}/">{e(gra["nazwa"])}</a></h3>\n'
        f'    <p>{e(gra["opis_krotki"]["pl"])}</p>\n'
        f'    {wersja}\n'
        f'    <p class="linki">{" · ".join(linki)}</p>\n'
        f'  </div>'
    )


def lista_notatek(notatki: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{e(n)}</li>" for n in notatki) + "</ul>"


def strona_gry(gra: dict) -> str:
    g = "../../"
    sklep = link_sklepu(gra)
    najnowsze = gra["wydania"][0] if gra["wydania"] else None
    czesci = []
    czesci.append(f'<h1>{e(gra["nazwa"])}</h1>')
    if najnowsze:
        czesci.append(
            f'<p class="cichy">Najnowsza wersja: <strong>{e(najnowsze["wersja"])}</strong> · '
            f'{e(SCIEZKI[najnowsze["sciezka"]][0])} · {e(data_pl(najnowsze["data"]))}</p>')
    for akapit in gra["opis"]["pl"]:
        czesci.append(f"<p>{e(akapit)}</p>")
    if sklep:
        czesci.append(f'<p><a class="przycisk" href="{e(sklep)}">Pobierz z Google Play</a></p>')
    else:
        czesci.append('<p class="cichy">Gra jest w fazie testów. Link do Google Play pojawi się tutaj w dniu premiery.</p>')

    if gra.get("zrzuty"):
        czesci.append("<h2>Zrzuty ekranu</h2>")
        czesci.append('<div class="zrzuty">')
        for z in gra["zrzuty"]:
            czesci.append(
                f'<figure><img src="{g}{e(z["plik"])}" alt="{e(z["opis"]["pl"])}" width="1280" height="720" loading="lazy">'
                f'<figcaption>{e(z["opis"]["pl"])}</figcaption></figure>')
        czesci.append("</div>")

    if gra["wydania"]:
        czesci.append("<h2>Co nowego</h2>")
        for w in gra["wydania"]:
            czesci.append(
                f'<h3 id="v{e(w["wersja"])}-{w["kod"]}">Wersja {e(w["wersja"])} '
                f'<span class="cichy">({e(data_pl(w["data"]))}, {e(SCIEZKI[w["sciezka"]][0])})</span></h3>')
            czesci.append(lista_notatek(w["notatki"]["pl"]))

    if gra.get("polityka"):
        czesci.append(f'<p><a href="{g}{e(gra["polityka"])}">Polityka prywatności gry {e(gra["nazwa"])}</a></p>')

    # English
    czesci.append(f'<h2 id="en">{e(gra.get("nazwa_en") or gra["nazwa"])} (English)</h2>')
    for akapit in gra["opis"]["en"]:
        czesci.append(f"<p>{e(akapit)}</p>")
    if najnowsze:
        czesci.append(
            f'<p class="cichy">Latest version: {e(najnowsze["wersja"])} · '
            f'{e(SCIEZKI[najnowsze["sciezka"]][1])} · {e(najnowsze["data"])}</p>')
        czesci.append(lista_notatek(najnowsze["notatki"]["en"]))
    if sklep:
        czesci.append(f'<p><a href="{e(sklep)}">Get it on Google Play</a></p>')

    tresc = "\n  ".join(czesci)
    obraz_og = adres(gra["okladka"]) if gra.get("okladka") else ""
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(gra["nazwa"])} · {FIRMA}</title>
<meta name="description" content="{e(gra["opis_krotki"]["pl"])}">
<meta property="og:title" content="{e(gra["nazwa"])}">
<meta property="og:description" content="{e(gra["opis_krotki"]["pl"])}">
<meta property="og:image" content="{e(obraz_og)}">
<link rel="alternate" type="application/rss+xml" title="Wydania gier" href="{g}feed.xml">
<link rel="stylesheet" href="{g}styl.css">
</head>
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z dane/gry/{e(gra["slug"])}.json. Nie edytuj ręcznie. -->
<main>
  <header>
    <a href="{g}index.html">← {FIRMA}</a>
    <a href="#en">English</a>
  </header>

  {tresc}

  <footer>© {rok(gra)} {FIRMA}</footer>
</main>
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
            "nazwa_en": g.get("nazwa_en"),
            "pakiet": g.get("pakiet"),
            "strona": adres(f"gry/{g['slug']}/"),
            "google_play": link_sklepu(g),
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
                "google_play": link_sklepu(g),
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
    (KORZEN / "api").mkdir(exist_ok=True)
    (KORZEN / "api" / "gry.json").write_text(
        json.dumps(api_gry(gry), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KORZEN / "api" / "wydania.json").write_text(
        json.dumps(json_feed(gry), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (KORZEN / "feed.xml").write_text(rss(gry), encoding="utf-8")
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

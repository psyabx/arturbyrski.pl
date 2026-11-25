"""Strony gier na PC dla dorosłych (np. River Fly Shop) z dane/gry-pc/<slug>.json.

Osobna ścieżka od gier dla dzieci: te gry nie trafiają do kart na stronie głównej,
do api/gry.json, api/wydania.json ani do feed.xml. Każda ma własne strony PL i EN:

  gry/<slug>/                     strona gry (PL)
  gry/<slug>/testy/               zgłoszenie do testów e-mailem (PL, noindex)
  gry/<slug>/prywatnosc/          prywatność zgłoszeń i statystyk (PL)
  gry/<slug>/feed.xml             dziennik rozwoju jako RSS (PL)
  gry/<slug>/z/<źródło>/          kopia strony gry dla kampanii (noindex, kanoniczny = strona gry)
  en/games/<slug>/                to samo po angielsku (playtest/, privacy/, feed.xml, from/<źródło>/)

Oraz gry/index.html: wszystkie gry (dla dzieci z dane/gry/ i na PC z dane/gry-pc/).

Cloudflare Web Analytics nie zapisuje parametrów UTM ani własnych zdarzeń, dlatego:
  - źródło ruchu z linku zewnętrznego rozpoznajemy po ścieżce kampanii (z/<źródło>/),
  - kliknięcie „Zgłoś się do testów” liczymy jako wejście na testy/ (przybliżenie, nie liczba zgłoszeń).
"""
from __future__ import annotations

import html
import json
import struct
from email.utils import format_datetime
import datetime as dt
from pathlib import Path
from urllib.parse import quote

KORZEN = Path(__file__).resolve().parent.parent
DANE_PC = KORZEN / "dane" / "gry-pc"
ADRES = "https://arturbyrski.pl"
FIRMA = "Artur Byrski Link Technologies"
FIRMA_ADRES = "ul. Kościelna 49, 34-100 Witanowice, Polska"
FIRMA_NIP = "5512278698"
EMAIL = "art.byrski@gmail.com"

# Ścieżki stron w obu językach.
SCIEZKI = {
    "pl": {"gra": "gry/{s}/", "testy": "gry/{s}/testy/", "prywatnosc": "gry/{s}/prywatnosc/",
           "feed": "gry/{s}/feed.xml", "kampania": "gry/{s}/z/{k}/",
           "artykuly": "gry/{s}/artykuly/", "artykul": "gry/{s}/artykuly/{k}/"},
    "en": {"gra": "en/games/{s}/", "testy": "en/games/{s}/playtest/", "prywatnosc": "en/games/{s}/privacy/",
           "feed": "en/games/{s}/feed.xml", "kampania": "en/games/{s}/from/{k}/",
           "artykuly": "en/games/{s}/articles/", "artykul": "en/games/{s}/articles/{k}/"},
}
# Artykuły o grze: dane/gry-pc/<slug>/artykuly/*.json (jeden plik = jeden artykuł w jednym języku).
POLA_ARTYKULU = ("slug", "jezyk", "opublikowano", "tytul", "opis", "tresc")
MIESIACE_PL = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
               "września", "października", "listopada", "grudnia"]
MIESIACE_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
               "September", "October", "November", "December"]


def e(t: str) -> str:
    return html.escape(str(t), quote=True)


def url(sciezka: str) -> str:
    return f"{ADRES}/{sciezka}"


def sc(jezyk: str, rodzaj: str, gra: dict, k: str = "") -> str:
    return SCIEZKI[jezyk][rodzaj].format(s=gra["slug"], k=k)


def data(iso: str, jezyk: str) -> str:
    d = dt.date.fromisoformat(iso)
    if jezyk == "pl":
        return f"{d.day} {MIESIACE_PL[d.month - 1]} {d.year}"
    return f"{d.day} {MIESIACE_EN[d.month - 1]} {d.year}"


def wczytaj_gry_pc() -> list[dict]:
    gry = []
    for plik in sorted(DANE_PC.glob("*.json")):
        g = json.loads(plik.read_text(encoding="utf-8"))
        g["_plik"] = plik.relative_to(KORZEN).as_posix()   # ukośniki także na Windows: plik wynikowy ma być taki sam w każdym systemie
        g["_artykuly"] = wczytaj_artykuly(g["slug"])
        gry.append(g)
    return gry


def wczytaj_artykuly(slug: str) -> list[dict]:
    """Wszystkie artykuły gry, także szkice (szkice sprawdzamy, ale nie publikujemy)."""
    artykuly = []
    for plik in sorted((DANE_PC / slug / "artykuly").glob("*.json")):
        a = json.loads(plik.read_text(encoding="utf-8"))
        a["_plik"] = plik.relative_to(KORZEN).as_posix()
        artykuly.append(a)
    return artykuly


def opublikowane(gra: dict, jezyk: str) -> list[dict]:
    """Opublikowane artykuły w danym języku, od najnowszego."""
    lista = [a for a in gra.get("_artykuly", []) if a.get("jezyk") == jezyk and not a.get("szkic")]
    return sorted(lista, key=lambda a: (a["opublikowano"], a["slug"]), reverse=True)


def sprawdz_artykuly(gra: dict) -> list[str]:
    bledy = []
    nazwy = {z["plik"] for z in gra["galeria"]}
    klucze = set()
    for a in gra.get("_artykuly", []):
        p = a["_plik"]
        brak = [k for k in POLA_ARTYKULU if not a.get(k)]
        if brak:
            bledy.append(f"{p}: brak pól {', '.join(brak)}")
            continue
        if a["jezyk"] not in ("pl", "en"):
            bledy.append(f"{p}: jezyk musi być pl albo en")
        try:
            dt.date.fromisoformat(a["opublikowano"])
            if a.get("zaktualizowano"):
                dt.date.fromisoformat(a["zaktualizowano"])
        except ValueError:
            bledy.append(f"{p}: data ma mieć postać RRRR-MM-DD")
        if (a["jezyk"], a["slug"]) in klucze:
            bledy.append(f"{p}: powtórzony slug {a['slug']} ({a['jezyk']})")
        klucze.add((a["jezyk"], a["slug"]))
        for blok in a["tresc"]:
            if len(blok) != 1 or next(iter(blok)) not in ("h2", "p", "lista", "obraz"):
                bledy.append(f"{p}: blok treści ma mieć jedno pole: h2, p, lista albo obraz")
            elif "obraz" in blok and blok["obraz"] not in nazwy:
                bledy.append(f"{p}: obraz spoza galerii gry: {blok['obraz']}")
    for a in gra.get("_artykuly", []):
        if a.get("para") and a.get("jezyk") in ("pl", "en"):
            drugi = "en" if a["jezyk"] == "pl" else "pl"
            if (drugi, a["para"]) not in klucze:
                bledy.append(f"{a['_plik']}: para {a['para']} nie istnieje w języku {drugi}")
    return bledy


def sprawdz(gra: dict) -> list[str]:
    bledy = []
    pliki = [gra["naglowek"]["plik"], gra["obraz_udostepniania"]]
    for z in gra["galeria"]:
        pliki += [obraz(z["plik"], gra), obraz(z["plik"], gra, maly=True)]
    for p in pliki:
        if not (KORZEN / p).is_file():
            bledy.append(f"{gra['slug']}: brak pliku {p}")
    nazwy = {z["plik"] for z in gra["galeria"]}
    for j in ("pl", "en"):
        for _, nazwa, _ in gra["teksty"][j].get("filary", []):
            if nazwa not in nazwy:
                bledy.append(f"{gra['slug']}: filar ({j}) ma obraz spoza galerii: {nazwa}")
    tr = gra.get("trailer")
    if tr:
        if not (tr.get("mp4") or tr.get("youtube")):
            bledy.append(f"{gra['slug']}: trailer potrzebuje pola mp4 albo youtube")
        if not tr.get("plakat"):
            bledy.append(f"{gra['slug']}: trailer potrzebuje pola plakat (lokalny obraz)")
        for pole in ("mp4", "plakat"):
            if tr.get(pole) and not (KORZEN / tr[pole]).is_file():
                bledy.append(f"{gra['slug']}: brak pliku trailera {tr[pole]}")
    for w in gra["dziennik"]:
        if w.get("obraz") and w["obraz"] not in nazwy:
            bledy.append(f"{gra['slug']}: wpis {w['data']} ma obraz spoza galerii: {w['obraz']}")
    return bledy + sprawdz_artykuly(gra)


def sekcja_trailera(gra: dict, jezyk: str) -> str:
    """Miejsce na zwiastun: sekcja pojawia się dopiero, gdy w danych jest pole trailer.

    {"mp4": "img/gry/<slug>/zwiastun.mp4", "plakat": "img/gry/<slug>/zwiastun.jpg", "ai": true}  plik z tej domeny, albo
    {"youtube": "<id filmu>", "plakat": "img/gry/<slug>/zwiastun.jpg"}  YouTube wczytywany dopiero po kliknięciu
    (youtube-nocookie.com), więc samo wejście na stronę nie łączy się z Google.
    """
    tr = gra.get("trailer")
    if not tr:
        return ""
    t = gra["teksty"][jezyk]
    plakat = "/" + tr["plakat"]
    znaczek = f' <span class="znaczek-ai">{e(t["ai_znaczek"])}</span>' if tr.get("ai", True) else ""
    if tr.get("mp4"):
        film = (f'<video class="wideo" controls preload="none" aria-label="{e(t.get("wideo_nazwa") or t["wideo_tytul"])}" poster="{e(plakat)}" width="1280" height="720">'
                f'<source src="/{e(tr["mp4"])}" type="video/mp4"></video>')
    else:
        yt = e(tr["youtube"])
        film = (f'<a class="wideo wideo-yt" href="https://www.youtube.com/watch?v={yt}" data-yt="{yt}">'
                f'<img src="{e(plakat)}" alt="{e(t["wideo_tytul"])}" width="1280" height="720" loading="lazy">'
                f'<span class="wideo-play">▶ {e(t["wideo_youtube"])}</span></a>'
                f'<p class="cichy">{e(t["wideo_zgoda"])}</p>'
                '<script>document.querySelectorAll(".wideo-yt").forEach(function(a){a.addEventListener("click",'
                'function(ev){ev.preventDefault();var f=document.createElement("iframe");'
                'f.src="https://www.youtube-nocookie.com/embed/"+encodeURIComponent(a.dataset.yt)+"?autoplay=1&rel=0";'
                'f.allow="autoplay; encrypted-media; picture-in-picture; fullscreen";f.allowFullscreen=true;'
                'f.title=a.querySelector("img").alt;f.className="wideo";a.replaceWith(f);});});</script>')
    return (f'<section id="zwiastun"><div class="wrap">\n  <h2>{e(t["wideo_tytul"])}</h2>\n'
            f'  <p>{e(t["wideo_opis"])}{znaczek}</p>\n'
            f'  {film}\n</div></section>\n')


def filary(gra: dict, jezyk: str) -> str:
    t = gra["teksty"][jezyk]
    if not t.get("filary"):
        return ""
    gal = {z["plik"]: z for z in gra["galeria"]}
    wspolny = wszystkie_ai(gra)
    znaczek = f'<span class="znaczek-ai">{e(t["ai_znaczek"])}</span>'
    wspolny_znaczek = f'  <p class="filary-ai">{znaczek}</p>\n' if wspolny else ""
    karty = []
    for tytul, nazwa, tekst in t["filary"]:
        z = gal[nazwa]
        karty.append(
            f'<li><img src="/{obraz(nazwa, gra, maly=True)}" alt="{e(alt(z, jezyk))}" width="800" height="450">'
            f'<div><h3>{e(tytul)}</h3><p>{e(tekst)}</p>'
            f'{znaczek if z.get("ai") and not wspolny else ""}</div></li>')
    return (f'<section id="filary" class="filary"><div class="wrap">\n'
            f'  <h2 class="ukryty">{e(t["filary_tytul"])}</h2>\n'
            f'  <ol>{"".join(karty)}</ol>\n'
            f'{wspolny_znaczek}'
            f'</div></section>\n')


def wszystkie_ai(gra: dict) -> bool:
    """Gdy każdy zrzut ma tymczasową grafikę AI, strona pokazuje jeden wspólny znaczek przy filarach i uwagę
    nad galerią, zamiast znaczka pod każdym obrazem. W galerii mieszanej znaczek dostaje każdy zrzut z AI."""
    return all(z.get("ai") for z in gra["galeria"])


def alt(zrzut: dict, jezyk: str) -> str:
    """Tekst zastępczy zrzutu: pole alt opisuje, co widać na obrazie; bez niego zostaje krótki podpis z galerii."""
    return (zrzut.get("alt") or {}).get(jezyk) or zrzut["opis"][jezyk]


def czas_mp4(plik: Path) -> int | None:
    """Długość filmu MP4 w sekundach, odczytana z nagłówka mvhd. Dzięki temu czas w danych strukturalnych
    zawsze zgadza się z plikiem, także po podmianie zwiastuna."""
    with plik.open("rb") as f:
        koniec = plik.stat().st_size
        while f.tell() < koniec:
            naglowek = f.read(8)
            if len(naglowek) < 8:
                return None
            rozmiar, typ = struct.unpack(">I4s", naglowek)
            poczatek = f.tell() - 8
            if rozmiar == 1:
                rozmiar = struct.unpack(">Q", f.read(8))[0]
            elif rozmiar == 0:
                rozmiar = koniec - poczatek
            if typ == b"moov":
                koniec = poczatek + rozmiar      # mvhd leży wewnątrz moov: czytamy dalej jego zawartość
                continue
            if typ == b"mvhd":
                wersja = f.read(4)[0]
                if wersja == 1:
                    f.read(16)
                    skala, czas = struct.unpack(">IQ", f.read(12))
                else:
                    f.read(8)
                    skala, czas = struct.unpack(">II", f.read(8))
                return round(czas / skala) if skala else None
            if rozmiar < 8:
                return None
            f.seek(poczatek + rozmiar)
    return None


def obraz(nazwa: str, gra: dict, maly: bool = False) -> str:
    return f"img/gry/{gra['slug']}/{nazwa}{'-maly' if maly else ''}.webp"


def link_steam(gra: dict, jezyk: str) -> str | None:
    """Miejsce na przycisk Steam: pojawia się dopiero, gdy w danych jest steam_app_id."""
    app = gra.get("steam_app_id")
    if not app:
        return None
    kampania = "rfs-strona-gry" if jezyk == "pl" else "rfs-strona-gry-en"
    return (f"https://store.steampowered.com/app/{int(app)}/?utm_source=arturbyrski.pl"
            f"&utm_medium=strona&utm_campaign={kampania}")


def przycisk_steam(gra: dict, jezyk: str) -> str:
    link = link_steam(gra, jezyk)
    if not link:
        return ""
    napis = "Zobacz na Steamie" if jezyk == "pl" else "View on Steam"
    return f'<a class="przycisk przycisk-drugi" href="{e(link)}">{napis}</a>'


def mailto(gra: dict, jezyk: str) -> str:
    if jezyk == "pl":
        temat = f"{gra['nazwa']} – testy"
        tresc = ("Cześć,\n\nchcę zgłosić się do testów River Fly Shop.\n\n"
                 "Pytania nieobowiązkowe:\n"
                 "Jak łowię (muszkarz / inna metoda / nie łowię): \n"
                 "Mam komputer z Windows (tak / nie): \n")
    else:
        temat = f"{gra['nazwa']} – playtest"
        tresc = ("Hi,\n\nI would like to sign up for the River Fly Shop playtest.\n\n"
                 "Optional questions:\n"
                 "How I fish (fly fishing / other methods / I don't fish): \n"
                 "I have a Windows PC (yes / no): \n")
    return f"mailto:{EMAIL}?subject={quote(temat)}&body={quote(tresc)}"


# ---------- części HTML ----------

def head(gra: dict, jezyk: str, tytul: str, opis: str, kanoniczny: str, alternatywy: dict | None,
         noindex: bool = False, dane: dict | None = None) -> str:
    t = gra["teksty"][jezyk]
    linie = [
        "<!doctype html>",
        f'<html lang="{jezyk}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{e(tytul)}</title>",
        f'<meta name="description" content="{e(opis)}">',
    ]
    if noindex:
        linie.append('<meta name="robots" content="noindex, follow">')
    linie.append(f'<link rel="canonical" href="{e(kanoniczny)}">')
    if alternatywy:
        for j, adres_ in alternatywy.items():
            linie.append(f'<link rel="alternate" hreflang="{j}" href="{e(adres_)}">')
    linie += [
        '<meta property="og:type" content="website">',
        f'<meta property="og:locale" content="{"pl_PL" if jezyk == "pl" else "en_US"}">',
        f'<meta property="og:locale:alternate" content="{"en_US" if jezyk == "pl" else "pl_PL"}">',
        f'<meta property="og:site_name" content="{e(gra["nazwa"])}">',
        f'<meta property="og:url" content="{e(kanoniczny)}">',
        f'<meta property="og:title" content="{e(tytul)}">',
        f'<meta property="og:description" content="{e(opis)}">',
        f'<meta property="og:image" content="{e(url(gra["obraz_udostepniania"]))}">',
        f'<meta property="og:image:alt" content="{e(gra["naglowek"]["opis"][jezyk])}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<link rel="alternate" type="application/rss+xml" title="{e(gra["nazwa"])}: '
        f'{e(t["dziennik_tytul"])}" href="/{sc(jezyk, "feed", gra)}">',
        '<link rel="icon" href="/ikona.svg" type="image/svg+xml">',
        '<link rel="stylesheet" href="/styl-pc.css">',
    ]
    if dane:
        tekst = json.dumps(dane, ensure_ascii=False, indent=1).replace("</", "<\\/")
        linie.append(f'<script type="application/ld+json">\n{tekst}\n</script>')
    linie.append("</head>")
    return "\n".join(linie)


def pasek(gra: dict, jezyk: str, druga: str, kotwice: bool = True) -> str:
    t = gra["teksty"][jezyk]
    glowna = "/" + sc(jezyk, "gra", gra)
    ids = ["o-grze", "mechaniki", "galeria", "etap", "dziennik", "testy"]
    menu = list(zip(ids, t["menu"]))
    if gra.get("trailer"):
        menu.insert(1, ("zwiastun", t["wideo_tytul"]))
    pozycje = "".join(f'<a href="{"" if kotwice else glowna}#{i}">{e(n)}</a>' for i, n in menu)
    wszystkie = "/gry/"
    return (f'<header class="pasek"><div class="wrap">'
            f'<a class="logo" href="{glowna}">{e(gra["nazwa"])}</a>'
            f'<nav class="menu">{pozycje}'
            f'<a href="{wszystkie}">{e(t["inne_gry"])}</a>'
            f'<a href="/{druga}" hreflang="{"en" if jezyk == "pl" else "pl"}" '
            f'lang="{"en" if jezyk == "pl" else "pl"}">{e(t["jezyk_inny"])}</a></nav></div></header>')


def stopka(gra: dict, jezyk: str) -> str:
    t = gra["teksty"][jezyk]
    rss = "Dziennik (RSS)" if jezyk == "pl" else "Log (RSS)"
    return (f'<footer><div class="wrap"><span>© 2026 {FIRMA}</span>'
            f'<span><a href="/gry/">{e(t["inne_gry"])}</a> · '
            f'<a href="/{sc(jezyk, "prywatnosc", gra)}">{e(t["stopka_polityka"])}</a> · '
            f'<a href="/{sc(jezyk, "feed", gra)}">{rss}</a></span></div></footer>')


def dane_filmu(gra: dict, jezyk: str) -> dict | None:
    """Zwiastun jako VideoObject. Tylko fakty z danych i z pliku: data z pola trailer.data, czas z nagłówka MP4."""
    tr = gra.get("trailer")
    if not tr or not tr.get("data"):
        return None
    t = gra["teksty"][jezyk]
    film = {
        "@type": "VideoObject",
        "name": t.get("wideo_nazwa") or f'{gra["nazwa"]}: {t["wideo_tytul"]}',
        "description": t["wideo_opis"],
        "thumbnailUrl": url(tr["plakat"]),
        "uploadDate": tr["data"],
    }
    if tr.get("mp4"):
        film["contentUrl"] = url(tr["mp4"])
        sekundy = czas_mp4(KORZEN / tr["mp4"])
        if sekundy:
            film["duration"] = f"PT{sekundy // 60}M{sekundy % 60}S" if sekundy >= 60 else f"PT{sekundy}S"
    else:
        film["embedUrl"] = f'https://www.youtube-nocookie.com/embed/{tr["youtube"]}'
    return film


def firma_ld() -> dict:
    return {"@type": "Organization", "@id": ADRES + "/#firma", "name": FIRMA, "url": ADRES + "/"}


def tworca_ld(gra: dict, jezyk: str) -> dict | None:
    """Twórca gry jako Person. Opis tylko z danych (pole tworca), zatwierdzony przez Artura."""
    tw = gra.get("tworca")
    if not tw:
        return None
    return {"@type": "Person", "@id": ADRES + "/#tworca", "name": tw["imie"],
            "description": tw["opis"][jezyk], "url": ADRES + "/", "worksFor": {"@id": ADRES + "/#firma"}}


def zdanie_o_tworcy(gra: dict, jezyk: str) -> str:
    tw = gra.get("tworca")
    if not tw:
        return ""
    if jezyk == "pl":
        return f"Grę tworzy {tw['imie']}, {tw['opis']['pl']}."
    return f"Made by {tw['imie']}, {tw['opis']['en']}."


def dane_gry(gra: dict, jezyk: str) -> dict:
    """Dane strukturalne strony gry: gra (VideoGame ze zwiastunem), ścieżka nawigacji i częste pytania.
    Bez ocen, ceny i daty premiery, bo gra jest w produkcji."""
    t = gra["teksty"][jezyk]
    strona = url(sc(jezyk, "gra", gra))
    firma = firma_ld()
    tworca = tworca_ld(gra, jezyk)
    gra_ld = {
        "@type": "VideoGame",
        "@id": strona + "#gra",
        "name": gra["nazwa"],
        "url": strona,
        "description": t["seo_opis"],
        "inLanguage": ["pl", "en"],
        "image": url(gra["obraz_udostepniania"]),
        "screenshot": [url(obraz(z["plik"], gra)) for z in gra["galeria"]],
        "gamePlatform": "PC",
        "operatingSystem": "Windows",
        "applicationCategory": "Game",
        "genre": (["Simulation", "Fishing", "Fly fishing"] if jezyk == "en"
                  else ["Symulator", "Wędkarstwo", "Wędkarstwo muchowe"]),
        "creativeWorkStatus": "In development" if jezyk == "en" else "W produkcji",
        "author": [tworca, firma] if tworca else firma,
        "publisher": firma,
    }
    if gra.get("slowa_kluczowe", {}).get(jezyk):
        gra_ld["keywords"] = ", ".join(gra["slowa_kluczowe"][jezyk])
    if gra.get("profile"):
        gra_ld["sameAs"] = list(gra["profile"])
    film = dane_filmu(gra, jezyk)
    if film:
        gra_ld["trailer"] = film
    okruszki = [(FIRMA, ADRES + "/")]
    if jezyk == "pl":
        okruszki.append(("Gry", url("gry/")))
    okruszki.append((gra["nazwa"], strona))
    graf = [gra_ld, {
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": nazwa, "item": adres_}
                            for i, (nazwa, adres_) in enumerate(okruszki, 1)],
    }]
    if t.get("pytania"):
        graf.append({
            "@type": "FAQPage",
            "@id": strona + "#pytania",
            "inLanguage": jezyk,
            "mainEntity": [{"@type": "Question", "name": pytanie,
                            "acceptedAnswer": {"@type": "Answer", "text": odpowiedz}}
                           for pytanie, odpowiedz in t["pytania"]],
        })
    return {"@context": "https://schema.org", "@graph": graf}


def alternatywy(gra: dict, rodzaj: str) -> dict:
    pl, en = url(sc("pl", rodzaj, gra)), url(sc("en", rodzaj, gra))
    return {"pl": pl, "en": en, "x-default": en}


# ---------- strony ----------

def strona_gry(gra: dict, jezyk: str, blok_stat: str, kampania: str | None = None) -> str:
    t = gra["teksty"][jezyk]
    druga_j = "en" if jezyk == "pl" else "pl"
    kanoniczny = url(sc(jezyk, "gra", gra))
    tytul_roboczy = (f' <span class="roboczy">({e(t["tytul_roboczy"])})</span>'
                     if gra.get("tytul_roboczy") else "")
    n = gra["naglowek"]

    opis = "".join(f"<p>{e(p)}</p>" for p in t["opis"])
    mechaniki = "".join(f'<li><h3>{e(a)}</h3><p>{e(b)}</p></li>' for a, b in t["mechaniki"])
    w_pracy = "".join(f"<li>{e(x)}</li>" for x in t["w_pracy"])
    kafle = []
    for z in gra["galeria"]:
        znaczek = (f'<span class="znaczek-ai">{e(t["ai_znaczek"])}</span>'
                   if z.get("ai") and not wszystkie_ai(gra) else "")
        kafle.append(
            f'<figure><a href="/{obraz(z["plik"], gra)}">'
            f'<img src="/{obraz(z["plik"], gra, maly=True)}" alt="{e(alt(z, jezyk))}" '
            f'width="800" height="450" loading="lazy"></a>'
            f'<figcaption>{e(z["opis"][jezyk])}<br><span class="cichy">{e(data(z["data"], jezyk))}'
            f'</span> {znaczek}</figcaption></figure>')
    galeria = "".join(kafle)
    wpisy = []
    gal = {z["plik"]: z for z in gra["galeria"]}
    for w in gra["dziennik"]:
        ilustracja = ""
        if w.get("obraz"):
            z = gal[w["obraz"]]
            ilustracja = (f'<a class="wpis-obraz" href="/{obraz(z["plik"], gra)}">'
                          f'<img src="/{obraz(z["plik"], gra, maly=True)}" alt="{e(alt(z, jezyk))}" '
                          f'width="800" height="450" loading="lazy"></a>')
        wpisy.append(
            f'<article class="wpis" id="d-{e(w["data"])}">{ilustracja}<div>'
            f'<time datetime="{e(w["data"])}">{e(data(w["data"], jezyk))}</time>'
            f'<h3>{e(w["tytul"][jezyk])}</h3><p>{e(w["tekst"][jezyk])}</p></div></article>')
    dziennik = "".join(wpisy)
    pytania = ""
    if t.get("pytania"):
        pary = "".join(f'<div class="pytanie"><h3>{e(a)}</h3><p>{e(b)}</p></div>' for a, b in t["pytania"])
        pytania = (f'\n<section id="pytania"><div class="wrap waski">\n  <h2>{e(t["pytania_tytul"])}</h2>\n'
                   f'  {pary}\n</div></section>\n')
    testy = "/" + sc(jezyk, "testy", gra)
    steam = przycisk_steam(gra, jezyk)
    rss_napis = "Dziennik jako RSS" if jezyk == "pl" else "Log as RSS"

    if kampania:
        glowa = head(gra, jezyk, t["seo_tytul"], t["seo_opis"], kanoniczny, None, noindex=True)
    else:
        glowa = head(gra, jezyk, t["seo_tytul"], t["seo_opis"], kanoniczny, alternatywy(gra, "gra"),
                     dane=dane_gry(gra, jezyk))
    zrodlo = f" Kopia dla kampanii „{kampania}”." if kampania else ""
    return f"""{glowa}
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(gra["_plik"])}.{zrodlo} Nie edytuj ręcznie. -->
{pasek(gra, jezyk, sc(druga_j, "gra", gra))}
<main>
<section class="naglowek">
  <img src="/{e(n["plik"])}" alt="{e(n["opis"][jezyk])}" width="{n["szerokosc"]}" height="{n["wysokosc"]}">
  <div class="wrap">
    <h1>{e(gra["nazwa"])}{tytul_roboczy}</h1>
    <p class="haslo">{e(t.get("haslo") or t["podtytul"])}</p>
    {f'<p class="lead">{e(t["lead"])}</p>' if t.get("lead") else ""}
    <p class="status">{e(t["status"])}</p>
    <div class="przyciski"><a class="przycisk" href="{testy}">{e(t["zgloszenie_przycisk"])}</a>{steam}</div>
  </div>
</section>
{filary(gra, jezyk)}{sekcja_trailera(gra, jezyk)}
<section id="o-grze"><div class="wrap waski">
  {f'<h2>{e(t["o_grze_tytul"])}</h2>' if t.get("o_grze_tytul") else ""}
  {opis}
  {f'<p>{e(zdanie_o_tworcy(gra, jezyk))}</p>' if gra.get("tworca") else ""}
  <p class="cichy">{e(t["nazwa_uwaga"])}</p>
</div></section>

<section id="mechaniki"><div class="wrap">
  <h2>{e(t["mechaniki_tytul"])}</h2>
  <ul class="mechaniki">{mechaniki}</ul>
  <h3 class="w-pracy-tytul">{e(t["w_pracy_tytul"])}</h3>
  <ul class="w-pracy">{w_pracy}</ul>
</div></section>

<section id="galeria"><div class="wrap">
  <h2>{e(t["galeria_tytul"])}</h2>
  <p>{e(t["galeria_wstep"])}</p>
  <p class="uwaga-ai">{e(t["ai_uwaga"])}</p>
  <div class="galeria">{galeria}</div>
</div></section>

<section id="etap"><div class="wrap waski">
  <h2>{e(t["etap_tytul"])}</h2>
  <p>{e(t["etap"])}</p>
</div></section>
{pytania}{sekcja_artykulow(gra, jezyk)}
<section id="dziennik"><div class="wrap">
  <h2>{e(t["dziennik_tytul"])}</h2>
  <p>{e(t["dziennik_wstep"])} <a href="/{sc(jezyk, "feed", gra)}">{rss_napis}</a></p>
  {dziennik}
</div></section>

<section id="testy" class="testy"><div class="wrap waski">
  <h2>{e(t["testy_tytul"])}</h2>
  <p>{e(t["testy"])}</p>
  <div class="przyciski"><a class="przycisk" href="{testy}">{e(t["zgloszenie_przycisk"])}</a></div>
</div></section>
</main>
{stopka(gra, jezyk)}
{blok_stat}
</body>
</html>
"""


def strona_testow(gra: dict, jezyk: str, blok_stat: str) -> str:
    t = gra["teksty"][jezyk]
    druga_j = "en" if jezyk == "pl" else "pl"
    kanoniczny = url(sc(jezyk, "testy", gra))
    prywatnosc = "/" + sc(jezyk, "prywatnosc", gra)
    if jezyk == "pl":
        tytul = f"Zgłoś się do testów {gra['nazwa']}"
        opis = f"Zgłoszenie do przyszłych testów gry {gra['nazwa']} na PC: jeden e-mail, bez zakładania konta."
        tresc = f"""<h1>{e(tytul)}</h1>
  <p>{e(t["testy"])}</p>
  <ol class="kroki">
    <li>Kliknij przycisk poniżej. Otworzy się nowa wiadomość z gotowym tematem.</li>
    <li>Jeśli chcesz, odpowiedz na dwa krótkie pytania w treści. Nie są obowiązkowe.</li>
    <li>Wyślij wiadomość. Gdy testy ruszą, dostaniesz zaproszenie na ten adres.</li>
  </ol>
  <div class="przyciski"><a class="przycisk" href="{e(mailto(gra, "pl"))}">Napisz e-mail: zgłaszam się</a></div>
  <p class="cichy">Jeśli przycisk nie otwiera poczty, napisz na <strong>{EMAIL}</strong> z tematem „{e(gra["nazwa"])} – testy”.</p>
  <div class="ramka">
    <h2>Co dzieje się z Twoim adresem</h2>
    <ul>
      <li>Adres e-mail i treść wiadomości zbiera {FIRMA} tylko po to, żeby zaprosić Cię do testów {e(gra["nazwa"])} i dać znać o premierze.</li>
      <li>Nie zapisujemy Cię na newsletter, nie wysyłamy reklam i nie przekazujemy adresu nikomu.</li>
      <li>Trzymamy go do zakończenia testów i premiery gry. Możesz w każdej chwili poprosić o usunięcie: wystarczy odpisać „usuń”.</li>
    </ul>
    <p><a href="{prywatnosc}">Pełna informacja o prywatności zgłoszeń</a></p>
  </div>
  <p><a href="/{sc("pl", "gra", gra)}">← Wróć do strony gry</a></p>"""
    else:
        tytul = f"Sign up for the {gra['nazwa']} playtest"
        opis = f"Sign up for future playtests of {gra['nazwa']} on PC: one email, no account needed."
        tresc = f"""<h1>{e(tytul)}</h1>
  <p>{e(t["testy"])}</p>
  <ol class="kroki">
    <li>Click the button below. A new email with a ready subject line will open.</li>
    <li>If you like, answer two short questions in the message. They are optional.</li>
    <li>Send it. When playtesting starts, you will get an invitation at that address.</li>
  </ol>
  <div class="przyciski"><a class="przycisk" href="{e(mailto(gra, "en"))}">Send an email: sign me up</a></div>
  <p class="cichy">If the button does not open your email app, write to <strong>{EMAIL}</strong> with the subject “{e(gra["nazwa"])} – playtest”.</p>
  <div class="ramka">
    <h2>What happens to your address</h2>
    <ul>
      <li>{FIRMA} collects your email address and message only to invite you to the {e(gra["nazwa"])} playtest and to let you know about the release.</li>
      <li>We do not add you to a newsletter, send ads or share your address with anyone.</li>
      <li>We keep it until playtesting ends and the game is released. You can ask us to delete it at any time: just reply “delete”.</li>
    </ul>
    <p><a href="{prywatnosc}">Full privacy information for sign-ups</a></p>
  </div>
  <p><a href="/{sc("en", "gra", gra)}">← Back to the game page</a></p>"""
    glowa = head(gra, jezyk, tytul, opis, kanoniczny, alternatywy(gra, "testy"), noindex=True)
    return f"""{glowa}
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(gra["_plik"])}. Nie edytuj ręcznie. -->
{pasek(gra, jezyk, sc(druga_j, "testy", gra), kotwice=False)}
<main><section><div class="wrap waski">
  {tresc}
</div></section></main>
{stopka(gra, jezyk)}
{blok_stat}
</body>
</html>
"""


def strona_prywatnosci(gra: dict, jezyk: str, blok_stat: str) -> str:
    druga_j = "en" if jezyk == "pl" else "pl"
    kanoniczny = url(sc(jezyk, "prywatnosc", gra))
    n = e(gra["nazwa"])
    if jezyk == "pl":
        tytul = f"Prywatność: zgłoszenia do testów {gra['nazwa']}"
        opis = f"Jak traktujemy adresy e-mail osób zgłaszających się do testów {gra['nazwa']} i jak liczymy odwiedziny strony."
        tresc = f"""<h1>{e(tytul)}</h1>
  <p class="cichy">Obowiązuje od 22 listopada 2026.</p>
  <h2>Zgłoszenia do testów</h2>
  <ul>
    <li><strong>Kto jest administratorem:</strong> {FIRMA}, {FIRMA_ADRES}, NIP {FIRMA_NIP}, e-mail {EMAIL}.</li>
    <li><strong>Jakie dane:</strong> adres e-mail i to, co sam napiszesz w wiadomości (np. czy łowisz na muchę). Nic nie jest obowiązkowe poza adresem, z którego piszesz.</li>
    <li><strong>Po co:</strong> żeby zaprosić Cię do testów gry {n} i dać znać o jej premierze. Nie wysyłamy newslettera ani reklam.</li>
    <li><strong>Podstawa:</strong> Twoja zgoda, wyrażona wysłaniem wiadomości (art. 6 ust. 1 lit. a RODO). Możesz ją wycofać w każdej chwili, odpisując „usuń”.</li>
    <li><strong>Jak długo:</strong> do zakończenia testów i premiery gry, potem usuwamy zgłoszenia. Wcześniej, jeśli o to poprosisz.</li>
    <li><strong>Kto ma dostęp:</strong> tylko my. Wiadomości leżą w skrzynce pocztowej Gmail, więc technicznie przechowuje je Google jako dostawca poczty. Adresów nie sprzedajemy i nie przekazujemy nikomu.</li>
    <li><strong>Twoje prawa:</strong> dostęp do danych, ich poprawienie lub usunięcie, wycofanie zgody oraz skarga do Prezesa Urzędu Ochrony Danych Osobowych.</li>
  </ul>
  <h2>Statystyki odwiedzin</h2>
  <p>Strona liczy odwiedziny narzędziem Cloudflare Web Analytics. Nie używa ciasteczek, nie zapisuje adresów IP i nie rozpoznaje pojedynczych osób. Widzimy tylko zbiorcze liczby, np. ile osób odwiedziło stronę gry, z jakiej strony przyszły i ile razy ktoś otworzył stronę zgłoszenia. Wysłanych e-maili to narzędzie nie widzi.</p>
  <h2>Zmiany</h2>
  <p>Jeśli ta informacja się zmieni, nowa wersja pojawi się na tej stronie z nową datą.</p>"""
    else:
        tytul = f"Privacy: {gra['nazwa']} playtest sign-ups"
        opis = f"How we handle email addresses of people who sign up for the {gra['nazwa']} playtest, and how we count visits."
        tresc = f"""<h1>{e(tytul)}</h1>
  <p class="cichy">Effective from 22 November 2026.</p>
  <h2>Playtest sign-ups</h2>
  <ul>
    <li><strong>Controller:</strong> {FIRMA}, {FIRMA_ADRES}, VAT ID PL{FIRMA_NIP}, email {EMAIL}.</li>
    <li><strong>What data:</strong> your email address and whatever you write in the message (e.g. whether you fly fish). Nothing is required apart from the address you write from.</li>
    <li><strong>Why:</strong> to invite you to the {n} playtest and to let you know when the game is released. We do not send newsletters or ads.</li>
    <li><strong>Legal basis:</strong> your consent, given by sending the email (Art. 6(1)(a) GDPR). You can withdraw it at any time by replying “delete”.</li>
    <li><strong>How long:</strong> until playtesting ends and the game is released, then we delete sign-ups. Sooner, if you ask.</li>
    <li><strong>Who has access:</strong> only us. Messages are kept in a Gmail mailbox, so technically Google stores them as the email provider. We never sell or share addresses.</li>
    <li><strong>Your rights:</strong> access, correction or deletion of your data, withdrawal of consent, and a complaint to the Polish data protection authority (Prezes UODO).</li>
  </ul>
  <h2>Visit statistics</h2>
  <p>The site counts visits with Cloudflare Web Analytics. It uses no cookies, does not store IP addresses and does not identify individual people. We only see totals, such as how many people visited the game page, which site they came from and how many times the sign-up page was opened. The tool cannot see the emails you send.</p>
  <h2>Changes</h2>
  <p>If this information changes, the new version will appear on this page with a new date.</p>"""
    glowa = head(gra, jezyk, tytul, opis, kanoniczny, alternatywy(gra, "prywatnosc"))
    return f"""{glowa}
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(gra["_plik"])}. Nie edytuj ręcznie. -->
{pasek(gra, jezyk, sc(druga_j, "prywatnosc", gra), kotwice=False)}
<main><section><div class="wrap waski">
  {tresc}
</div></section></main>
{stopka(gra, jezyk)}
{blok_stat}
</body>
</html>
"""


# ---------- artykuły o grze ----------

NAPISY_ARTYKULOW = {
    "pl": {"tytul": "Artykuły", "wszystkie": "Wszystkie artykuły", "opublikowano": "Opublikowano",
           "zaktualizowano": "zaktualizowano", "wroc": "← Wróć do strony gry",
           "lista_opis": "Artykuły o grze {n}: jak powstaje, jak działa i skąd biorą się jej realia."},
    "en": {"tytul": "Articles", "wszystkie": "All articles", "opublikowano": "Published",
           "zaktualizowano": "updated", "wroc": "← Back to the game page",
           "lista_opis": "Articles about {n}: how it is made, how it works and where its details come from."},
}


def adres_artykulu(gra: dict, a: dict) -> str:
    return sc(a["jezyk"], "artykul", gra, a["slug"])


def para_artykulu(gra: dict, a: dict) -> dict | None:
    if not a.get("para"):
        return None
    drugi = "en" if a["jezyk"] == "pl" else "pl"
    return next((b for b in opublikowane(gra, drugi) if b["slug"] == a["para"]), None)


def data_artykulu(a: dict, jezyk: str) -> str:
    n = NAPISY_ARTYKULOW[jezyk]
    tekst = (f'{n["opublikowano"]} <time datetime="{e(a["opublikowano"])}">'
             f'{e(data(a["opublikowano"], jezyk))}</time>')
    if a.get("zaktualizowano"):
        tekst += (f', {n["zaktualizowano"]} <time datetime="{e(a["zaktualizowano"])}">'
                  f'{e(data(a["zaktualizowano"], jezyk))}</time>')
    return tekst


def sekcja_artykulow(gra: dict, jezyk: str) -> str:
    """Lista najnowszych artykułów na stronie gry. Pusta, dopóki nie ma żadnego artykułu."""
    lista = opublikowane(gra, jezyk)
    if not lista:
        return ""
    n = NAPISY_ARTYKULOW[jezyk]
    pozycje = "".join(
        f'<li><a href="/{adres_artykulu(gra, a)}">{e(a["tytul"])}</a><br><span class="cichy">{e(a["opis"])}</span></li>'
        for a in lista[:5])
    return (f'\n<section id="artykuly"><div class="wrap waski">\n  <h2>{n["tytul"]}</h2>\n'
            f'  <ul class="artykuly">{pozycje}</ul>\n'
            f'  <p><a href="/{sc(jezyk, "artykuly", gra)}">{n["wszystkie"]}</a></p>\n</div></section>\n')


def tresc_artykulu(gra: dict, a: dict) -> str:
    gal = {z["plik"]: z for z in gra["galeria"]}
    czesci = []
    for blok in a["tresc"]:
        if "h2" in blok:
            czesci.append(f"<h2>{e(blok['h2'])}</h2>")
        elif "p" in blok:
            czesci.append(f"<p>{e(blok['p'])}</p>")
        elif "lista" in blok:
            czesci.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in blok["lista"]) + "</ul>")
        elif "obraz" in blok:
            z = gal[blok["obraz"]]
            czesci.append(f'<figure><a href="/{obraz(z["plik"], gra)}"><img src="/{obraz(z["plik"], gra, maly=True)}" '
                          f'alt="{e(alt(z, a["jezyk"]))}" width="800" height="450" loading="lazy"></a>'
                          f'<figcaption>{e(z["opis"][a["jezyk"]])}</figcaption></figure>')
    return "\n  ".join(czesci)


def dane_artykulu(gra: dict, a: dict) -> dict:
    jezyk = a["jezyk"]
    strona = url(adres_artykulu(gra, a))
    tworca = tworca_ld(gra, jezyk)
    art = {
        "@type": "Article",
        "@id": strona + "#artykul",
        "headline": a["tytul"],
        "description": a["opis"],
        "inLanguage": jezyk,
        "datePublished": a["opublikowano"],
        "dateModified": a.get("zaktualizowano") or a["opublikowano"],
        "author": tworca or firma_ld(),
        "publisher": firma_ld(),
        "mainEntityOfPage": strona,
        "about": {"@id": url(sc(jezyk, "gra", gra)) + "#gra", "@type": "VideoGame", "name": gra["nazwa"]},
        "image": url(gra["obraz_udostepniania"]),
    }
    okruszki = [(FIRMA, ADRES + "/"), (gra["nazwa"], url(sc(jezyk, "gra", gra))),
                (NAPISY_ARTYKULOW[jezyk]["tytul"], url(sc(jezyk, "artykuly", gra))), (a["tytul"], strona)]
    return {"@context": "https://schema.org", "@graph": [art, {
        "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": nazwa, "item": adres_}
                            for i, (nazwa, adres_) in enumerate(okruszki, 1)],
    }]}


def strona_artykulu(gra: dict, a: dict, blok_stat: str) -> str:
    jezyk = a["jezyk"]
    druga_j = "en" if jezyk == "pl" else "pl"
    kanoniczny = url(adres_artykulu(gra, a))
    para = para_artykulu(gra, a)
    alternatywy_ = None
    druga = sc(druga_j, "gra", gra)
    if para:
        druga = adres_artykulu(gra, para)
        pl, en = (a, para) if jezyk == "pl" else (para, a)
        alternatywy_ = {"pl": url(adres_artykulu(gra, pl)), "en": url(adres_artykulu(gra, en)),
                        "x-default": url(adres_artykulu(gra, en))}
    glowa = head(gra, jezyk, f'{a["tytul"]} · {gra["nazwa"]}', a["opis"], kanoniczny, alternatywy_,
                 dane=dane_artykulu(gra, a))
    podpis = f'<p>{e(zdanie_o_tworcy(gra, jezyk))}</p>' if gra.get("tworca") else ""
    return f"""{glowa}
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(a["_plik"])}. Nie edytuj ręcznie. -->
{pasek(gra, jezyk, druga, kotwice=False)}
<main><article class="artykul"><div class="wrap waski">
  <h1>{e(a["tytul"])}</h1>
  <p class="cichy">{data_artykulu(a, jezyk)}</p>
  <p class="lead">{e(a["opis"])}</p>
  {tresc_artykulu(gra, a)}
  {podpis}
  <p><a href="/{sc(jezyk, "artykuly", gra)}">{NAPISY_ARTYKULOW[jezyk]["wszystkie"]}</a> · <a href="/{sc(jezyk, "gra", gra)}">{NAPISY_ARTYKULOW[jezyk]["wroc"]}</a></p>
</div></article></main>
{stopka(gra, jezyk)}
{blok_stat}
</body>
</html>
"""


def strona_listy_artykulow(gra: dict, jezyk: str, blok_stat: str) -> str:
    n = NAPISY_ARTYKULOW[jezyk]
    druga_j = "en" if jezyk == "pl" else "pl"
    kanoniczny = url(sc(jezyk, "artykuly", gra))
    oba = bool(opublikowane(gra, druga_j))
    alternatywy_ = alternatywy(gra, "artykuly") if oba else None
    druga = sc(druga_j, "artykuly" if oba else "gra", gra)
    tytul = f'{n["tytul"]} · {gra["nazwa"]}'
    opis = n["lista_opis"].format(n=gra["nazwa"])
    pozycje = "".join(
        f'<article class="wpis"><div><p class="cichy">{data_artykulu(a, jezyk)}</p>'
        f'<h2><a href="/{adres_artykulu(gra, a)}">{e(a["tytul"])}</a></h2><p>{e(a["opis"])}</p></div></article>'
        for a in opublikowane(gra, jezyk))
    dane = {"@context": "https://schema.org", "@type": "CollectionPage", "name": tytul, "url": kanoniczny,
            "inLanguage": jezyk, "about": {"@id": url(sc(jezyk, "gra", gra)) + "#gra"}, "publisher": firma_ld()}
    glowa = head(gra, jezyk, tytul, opis, kanoniczny, alternatywy_, dane=dane)
    return f"""{glowa}
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z {e(gra["slug"])}/artykuly/*.json. Nie edytuj ręcznie. -->
{pasek(gra, jezyk, druga, kotwice=False)}
<main><section><div class="wrap waski">
  <h1>{e(n["tytul"])}: {e(gra["nazwa"])}</h1>
  <p>{e(opis)}</p>
  {pozycje}
  <p><a href="/{sc(jezyk, "gra", gra)}">{n["wroc"]}</a></p>
</div></section></main>
{stopka(gra, jezyk)}
{blok_stat}
</body>
</html>
"""


def rss(gra: dict, jezyk: str) -> str:
    t = gra["teksty"][jezyk]

    def x(s: str) -> str:
        return html.escape(str(s), quote=False)

    strona = url(sc(jezyk, "gra", gra))
    elementy = []
    for w in gra["dziennik"]:
        d = dt.datetime.fromisoformat(w["data"] + "T12:00:00+00:00")
        elementy.append(
            "    <item>\n"
            f"      <title>{x(w['tytul'][jezyk])}</title>\n"
            f"      <link>{x(strona)}#d-{x(w['data'])}</link>\n"
            f"      <guid isPermaLink=\"false\">{x(gra['slug'])}-{jezyk}-{x(w['data'])}</guid>\n"
            f"      <pubDate>{format_datetime(d)}</pubDate>\n"
            f"      <description>{x(w['tekst'][jezyk])}</description>\n"
            "    </item>")
    return ('<?xml version="1.0" encoding="utf-8"?>\n<rss version="2.0">\n  <channel>\n'
            f"    <title>{x(gra['nazwa'])}: {x(t['dziennik_tytul'])}</title>\n"
            f"    <link>{x(strona)}</link>\n"
            f"    <description>{x(t['dziennik_wstep'])}</description>\n"
            f"    <language>{jezyk}</language>\n"
            + "\n".join(elementy) + "\n  </channel>\n</rss>\n")


# ---------- strona zbiorcza /gry/ ----------

def strona_wszystkich_gier(gry_dzieci: list[dict], gry_pc: list[dict], pasek_html: str, stopka_html: str,
                           blok_stat: str) -> str:
    def karta_dziecieca(g: dict) -> str:
        s = e(g["slug"])
        obraz_ = (f'<a href="/gry/{s}/"><img src="/{e(g["okladka"])}" alt="{e(g["nazwa"])}: ekran gry dla dzieci" '
                  f'width="1280" height="720" loading="lazy"></a>') if g.get("okladka") else ""
        wiek = f'<li>dla dzieci {e(g["wiek"])}</li>' if g.get("wiek") else ""
        return (f'<article class="gra">{obraz_}<div class="gra-opis jasne">'
                f'<h3><a href="/gry/{s}/">{e(g["nazwa"])}</a></h3>'
                f'<p>{e(g["opis_krotki"]["pl"])}</p>'
                f'<ul class="znaczki">{wiek}<li>Android</li></ul>'
                f'<p><a href="/gry/{s}/">Więcej o grze</a></p></div></article>')

    def karta_pc(g: dict) -> str:
        t = g["teksty"]["pl"]
        s = sc("pl", "gra", g)
        n = g["naglowek"]
        roboczy = ' <span class="roboczy">(tytuł roboczy)</span>' if g.get("tytul_roboczy") else ""
        return (f'<article class="gra"><a href="/{s}"><img src="/{e(n["plik"])}" alt="{e(n["opis"]["pl"])}" '
                f'width="{n["szerokosc"]}" height="{n["wysokosc"]}" loading="lazy"></a>'
                f'<div class="gra-opis jasne"><h3><a href="/{s}">{e(g["nazwa"])}</a>{roboczy}</h3>'
                f'<p>{e(t["opis"][0])}</p>'
                f'<ul class="znaczki"><li>dla dorosłych</li><li>{e(g["platforma"])}</li><li>w produkcji</li></ul>'
                f'<p><a href="/{s}">Jak powstaje gra</a> · <a href="/{sc("en", "gra", g)}" hreflang="en" lang="en">English</a></p>'
                f'</div></article>')

    dzieci = "\n".join(karta_dziecieca(g) for g in gry_dzieci)
    pc = "\n".join(karta_pc(g) for g in gry_pc)
    dane = {
        "@context": "https://schema.org", "@type": "CollectionPage", "name": "Gry Artura Byrskiego",
        "url": url("gry/"), "inLanguage": "pl",
        "publisher": {"@type": "Organization", "@id": ADRES + "/#firma", "name": FIRMA, "url": ADRES + "/"},
    }
    dane_txt = json.dumps(dane, ensure_ascii=False, indent=1).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wszystkie gry · Artur Byrski Link Technologies</title>
<meta name="description" content="Gry niezależnego twórcy Artura Byrskiego: spokojne gry na telefon dla dzieci (Ortopotwory, Szlafmyce) i River Fly Shop, gra na PC dla dorosłych w produkcji.">
<link rel="canonical" href="{url("gry/")}">
<meta property="og:type" content="website">
<meta property="og:locale" content="pl_PL">
<meta property="og:site_name" content="Artur Byrski Link Technologies">
<meta property="og:url" content="{url("gry/")}">
<meta property="og:title" content="Wszystkie gry Artura Byrskiego">
<meta property="og:description" content="Gry na telefon dla dzieci i gra na PC dla dorosłych w produkcji.">
<script type="application/ld+json">
{dane_txt}
</script>
<link rel="icon" href="/ikona.svg" type="image/svg+xml">
<link rel="stylesheet" href="/styl.css">
</head>
<body>
<!-- Plik wygenerowany przez narzedzia/strona.py z dane/gry/*.json i dane/gry-pc/*.json. Nie edytuj ręcznie. -->
{pasek_html}
<main>
<section><div class="wrap">
  <h1>Wszystkie gry</h1>
  <p>Robię gry jako niezależny twórca. Są wśród nich spokojne gry na telefon dla dzieci i gra na komputer dla dorosłych wędkarzy.</p>
  <h2 class="grupa-gier">Dla dzieci (Android)</h2>
  <p class="cichy">Bez reklam, bez zbierania danych, offline. Część za darmo, resztę odblokowuje jeden zakup za bramką dla rodziców.</p>
{dzieci}
  <h2 class="grupa-gier">Dla dorosłych (PC, w produkcji)</h2>
  <p class="cichy">Ta gra nie jest jeszcze dostępna.</p>
{pc}
</div></section>
</main>
{stopka_html}
{blok_stat}
</body>
</html>
"""


def zbuduj_pc(gry_dzieci: list[dict], blok_stat: str, pasek_html: str, stopka_html: str) -> list[tuple[str, str | None, str]]:
    """Generuje strony gier PC i /gry/. Zwraca wpisy do sitemap.xml: (adres, data zmian, priorytet)."""
    gry_pc = wczytaj_gry_pc()
    bledy = [b for g in gry_pc for b in sprawdz(g)]
    if bledy:
        raise SystemExit("\n".join(bledy))
    wpisy: list[tuple[str, str | None, str]] = [(url("gry/"), None, "0.7")]

    def zapisz(sciezka: str, tekst: str) -> None:
        plik = KORZEN / sciezka
        if sciezka.endswith("/"):
            plik = plik / "index.html"
        plik.parent.mkdir(parents=True, exist_ok=True)
        plik.write_text(tekst, encoding="utf-8")

    for g in gry_pc:
        ostatni = g["dziennik"][0]["data"] if g["dziennik"] else None
        for j in ("pl", "en"):
            zapisz(sc(j, "gra", g), strona_gry(g, j, blok_stat))
            zapisz(sc(j, "testy", g), strona_testow(g, j, blok_stat))
            zapisz(sc(j, "prywatnosc", g), strona_prywatnosci(g, j, blok_stat))
            zapisz(sc(j, "feed", g), rss(g, j))
            for k in g.get("kampanie", []):
                zapisz(sc(j, "kampania", g, k), strona_gry(g, j, blok_stat, kampania=k))
            wpisy.append((url(sc(j, "gra", g)), ostatni, "0.9"))
            wpisy.append((url(sc(j, "prywatnosc", g)), None, "0.3"))
            artykuly = opublikowane(g, j)
            if artykuly:
                zapisz(sc(j, "artykuly", g), strona_listy_artykulow(g, j, blok_stat))
                wpisy.append((url(sc(j, "artykuly", g)), artykuly[0]["opublikowano"], "0.7"))
                for a in artykuly:
                    zapisz(adres_artykulu(g, a), strona_artykulu(g, a, blok_stat))
                    wpisy.append((url(adres_artykulu(g, a)), a.get("zaktualizowano") or a["opublikowano"], "0.8"))
    zapisz("gry/", strona_wszystkich_gier(gry_dzieci, gry_pc, pasek_html, stopka_html, blok_stat))
    return wpisy

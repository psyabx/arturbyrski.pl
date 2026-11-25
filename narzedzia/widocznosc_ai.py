#!/usr/bin/env python3
"""Mierzy, czy czaty AI z wyszukiwaniem w sieci znają grę River Fly Shop i cytują arturbyrski.pl.

Zadaje te same pytania (dane/widocznosc-ai.json) czatom Anthropic, OpenAI, Google Gemini i Perplexity,
każde bez kontekstu i kilka razy, bo odpowiedzi nie są powtarzalne. Zapisuje surowe odpowiedzi (JSONL)
i raport Markdown: wzmianki o grze, cytowania arturbyrski.pl, pozycję na liście, rozpoznanie błędnej
nazwy i porównanie z poprzednim przebiegiem.

Repozytorium jest publiczne (GitHub Pages), więc wyniki zapisujemy POZA nim: domyślnie
~/.rfs-widocznosc/<data_godzina>/, inny katalog podaje się w --wyniki. Katalog w repozytorium jest
odrzucany. Klucze API tylko ze zmiennych środowiskowych; dostawca bez klucza jest pomijany.

Użycie:
  python3 narzedzia/widocznosc_ai.py --proba                 plan i szacowany koszt, bez zapytań
  python3 narzedzia/widocznosc_ai.py                         pełny pomiar (dostawcy z kluczami)
  python3 narzedzia/widocznosc_ai.py --dostawcy perplexity,gemini --powtorzenia 1
  python3 narzedzia/widocznosc_ai.py --raport ~/.rfs-widocznosc/2026-12-01_080000   raport od nowa
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

KORZEN = Path(__file__).resolve().parent.parent
DANE = KORZEN / "dane" / "widocznosc-ai.json"
DOMYSLNE_WYNIKI = Path.home() / ".rfs-widocznosc"

PLIK_ODPOWIEDZI = "widocznosc-odpowiedzi.jsonl"
PLIK_RAPORTU = "widocznosc-raport.md"
PLIK_PODSUMOWANIA = "widocznosc-podsumowanie.json"
PLIK_OCENY = "widocznosc-ocena.csv"

KOLEJNOSC_DOSTAWCOW = ["anthropic", "openai", "gemini", "perplexity"]
NAZWY_DOSTAWCOW = {"anthropic": "Anthropic (Claude)", "openai": "OpenAI (ChatGPT)",
                   "gemini": "Google Gemini", "perplexity": "Perplexity"}


class BladApi(Exception):
    """Błąd zapytania do dostawcy z czytelnym opisem (bez klucza)."""


# ---------------------------------------------------------------------------
# Wykrywanie: wzmianki, cytowania, pozycja na liście (bez sieci, testowane)
# ---------------------------------------------------------------------------

def bez_ogonkow(tekst: str) -> str:
    """Małe litery bez znaków diakrytycznych, żeby „Shóp” i „shop” porównywać tak samo."""
    t = unicodedata.normalize("NFKD", tekst.replace("ł", "l").replace("Ł", "L"))
    return "".join(z for z in t if not unicodedata.combining(z)).lower()


def wzorzec_wariantu(wariant: str) -> re.Pattern:
    """„River Fly Shop” i „RiverFlyShop” → wzorzec dopuszczający spację, łącznik lub nic między słowami."""
    slowa = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", wariant)
    slowa = [bez_ogonkow(s) for s in slowa]
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-_.]*".join(map(re.escape, slowa)) + r"(?![a-z0-9])")


def wykryj_wzmianke(tekst: str, gra: dict) -> dict:
    """Czy odpowiedź wymienia grę. Warianty rozmyte liczą się jako wzmianka, ale są oznaczone osobno."""
    t = bez_ogonkow(tekst or "")
    for wariant in gra.get("warianty", []) + [gra["nazwa"]]:
        if wzorzec_wariantu(wariant).search(t):
            return {"wzmianka": True, "rozmyta": False, "wariant": wariant}
    for wariant in gra.get("warianty_rozmyte", []):
        if wzorzec_wariantu(wariant).search(t):
            return {"wzmianka": True, "rozmyta": True, "wariant": wariant}
    return {"wzmianka": False, "rozmyta": False, "wariant": None}


def wymienia_tworce(tekst: str, gra: dict) -> bool:
    t = bez_ogonkow(tekst or "")
    return any(wzorzec_wariantu(w).search(t) for w in gra.get("tworca", []))


def host_z_domeny(adres: str, domeny: list[str]) -> bool:
    """Czy adres (albo sama nazwa hosta) należy do jednej z domen, łącznie z subdomenami (www)."""
    if not adres:
        return False
    host = urlparse(adres if "//" in adres else "//" + adres).hostname or ""
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith("." + d) for d in domeny)


def zrodlo_z_domeny(zrodlo: dict, domeny: list[str]) -> bool:
    """Gemini zwraca czasem adres przekierowania Google, a domenę źródła tylko w tytule."""
    if host_z_domeny(zrodlo.get("url", ""), domeny):
        return True
    tytul = (zrodlo.get("tytul") or "").strip().lower()
    return bool(tytul) and " " not in tytul and host_z_domeny(tytul, domeny)


def wykryj_cytowanie(rekord: dict, domeny: list[str]) -> dict:
    tekst = bez_ogonkow(rekord.get("tekst") or "")
    return {
        "cytowanie": any(zrodlo_z_domeny(z, domeny) for z in rekord.get("zrodla", [])),
        "w_wyszukiwaniu": any(zrodlo_z_domeny(z, domeny) for z in rekord.get("wyniki_wyszukiwania", [])),
        "domena_w_tekscie": any(re.search(r"(?<![a-z0-9.-])" + re.escape(d), tekst) for d in domeny),
    }


_POZYCJA = re.compile(r"^( ?)(?:(?:\*\*)?(\d+)[.)]|([-*+•])|(#{1,4}))\s+(.+)$")


def pozycja_na_liscie(tekst: str, gra: dict) -> int | None:
    """Miejsce gry na liście w odpowiedzi (1 = pierwsza), albo None, gdy nie da się ustalić.

    W liście numerowanej bierzemy numer, który widzi czytelnik. Przy punktorach i nagłówkach liczymy
    elementy tego samego rodzaju (nagłówki tego samego poziomu) i tylko te bez wcięcia, żeby podpunkty
    pod inną grą nie przesuwały pozycji.
    """
    elementy = []
    for linia in (tekst or "").splitlines():
        m = _POZYCJA.match(linia)
        if not m:
            continue
        rodzaj = "numer" if m.group(2) else ("punkt" if m.group(3) else "naglowek" + m.group(4))
        elementy.append((rodzaj, m.group(2), m.group(5)))
    for i, (rodzaj, numer, tresc) in enumerate(elementy):
        if wykryj_wzmianke(tresc, gra)["wzmianka"]:
            if numer:
                return int(numer)
            return sum(1 for r, _, _ in elementy[: i + 1] if r == rodzaj)
    return None


def fragment(tekst: str, gra: dict, szer: int = 160) -> str:
    """Wycinek odpowiedzi wokół wzmianki, do ręcznej oceny w raporcie."""
    t = bez_ogonkow(tekst or "")
    for wariant in gra.get("warianty", []) + [gra["nazwa"]] + gra.get("warianty_rozmyte", []):
        m = wzorzec_wariantu(wariant).search(t)
        if m:
            a, b = max(0, m.start() - szer), min(len(tekst), m.end() + szer)
            return ("…" if a else "") + " ".join(tekst[a:b].split()) + ("…" if b < len(tekst) else "")
    return ""


def ocen(rekord: dict, gra: dict) -> dict:
    """Wszystkie automatyczne wskaźniki jednej odpowiedzi. Liczone przy raporcie, nie zapisywane w JSONL,
    więc poprawka wykrywania działa też na starych przebiegach (--raport)."""
    w = wykryj_wzmianke(rekord.get("tekst", ""), gra)
    c = wykryj_cytowanie(rekord, gra.get("domeny", []))
    return {**w, **c,
            "pozycja": pozycja_na_liscie(rekord.get("tekst", ""), gra) if w["wzmianka"] else None,
            "tworca": wymienia_tworce(rekord.get("tekst", ""), gra)}


# ---------------------------------------------------------------------------
# Dostawcy: zapytanie HTTP (urllib) i odczyt odpowiedzi
# ---------------------------------------------------------------------------

def wyslij(url: str, naglowki: dict, cialo: dict, timeout: int = 300, proby: int = 3) -> dict:
    """POST z JSON. Ponawia po 429 i błędach serwera; inne błędy zgłasza z treścią odpowiedzi."""
    dane = json.dumps(cialo).encode("utf-8")
    for proba in range(proby):
        zad = urllib.request.Request(url, data=dane, method="POST",
                                     headers={"Content-Type": "application/json", **naglowki})
        try:
            with urllib.request.urlopen(zad, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            tresc = e.read().decode("utf-8", "replace")[:600]
            if e.code in (408, 409, 429, 500, 502, 503, 504, 529) and proba < proby - 1:
                czekaj = int(e.headers.get("retry-after") or 0) or 10 * (proba + 1)
                print(f"    HTTP {e.code}, ponawiam za {czekaj} s")
                time.sleep(min(czekaj, 120))
                continue
            if e.code in (401, 403):
                raise BladApi(f"HTTP {e.code}: klucz odrzucony albo brak dostępu do modelu. {tresc}")
            raise BladApi(f"HTTP {e.code}: {tresc}")
        except (urllib.error.URLError, TimeoutError) as e:
            if proba < proby - 1:
                time.sleep(10 * (proba + 1))
                continue
            raise BladApi(f"Brak połączenia: {e}")
    raise BladApi("Nie udało się po kilku próbach")


def _liczba(slownik: dict | None, *klucze) -> int | None:
    for k in klucze:
        if isinstance(slownik, dict) and isinstance(slownik.get(k), (int, float)):
            return int(slownik[k])
    return None


def wynik_pusty() -> dict:
    return {"tekst": "", "zrodla": [], "wyniki_wyszukiwania": [], "wyszukiwania": 0,
            "tokeny_we": None, "tokeny_wy": None, "model": None, "koszt_dostawcy_usd": None}


def czytaj_anthropic(odpowiedzi: list[dict]) -> dict:
    """Messages API z web_search: tekst z bloków text, cytowania w text.citations (web_search_result_location)."""
    w = wynik_pusty()
    teksty, we, wy = [], 0, 0
    for o in odpowiedzi:
        w["model"] = o.get("model") or w["model"]
        for blok in o.get("content", []):
            if blok.get("type") == "text":
                teksty.append(blok.get("text", ""))
                for c in blok.get("citations") or []:
                    if c.get("url"):
                        w["zrodla"].append({"url": c["url"], "tytul": c.get("title")})
            elif blok.get("type") == "web_search_tool_result" and isinstance(blok.get("content"), list):
                for r in blok["content"]:
                    if r.get("url"):
                        w["wyniki_wyszukiwania"].append({"url": r["url"], "tytul": r.get("title")})
        u = o.get("usage") or {}
        we += (u.get("input_tokens") or 0) + (u.get("cache_read_input_tokens") or 0) \
            + (u.get("cache_creation_input_tokens") or 0)
        wy += u.get("output_tokens") or 0
        w["wyszukiwania"] += _liczba(u.get("server_tool_use"), "web_search_requests") or 0
    w["tekst"] = "".join(teksty).strip()
    w["tokeny_we"], w["tokeny_wy"] = we, wy
    return w


def zapytaj_anthropic(pytanie: str, cfg: dict, klucz: str) -> dict:
    naglowki = {"x-api-key": klucz, "anthropic-version": "2026-10-21",
                "anthropic-beta": "server-side-fallback-2026-07-01"}
    wiadomosci = [{"role": "user", "content": pytanie}]
    cialo = {"model": cfg["model"], "max_tokens": 16000, "messages": wiadomosci,
             "tools": [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}],
             # Gdy klasyfikator bezpieczeństwa odmówi, API samo ponawia na modelu zapasowym.
             "fallbacks": "default"}
    odpowiedzi = []
    for _ in range(4):
        o = wyslij("https://api.anthropic.com/v1/messages", naglowki, cialo)
        odpowiedzi.append(o)
        if o.get("stop_reason") == "refusal":
            raise BladApi(f"Odmowa modelu: {(o.get('stop_details') or {}).get('category')}")
        if o.get("stop_reason") != "pause_turn":
            break
        # Długie wyszukiwanie: odsyłamy dotychczasową odpowiedź, serwer kontynuuje od miejsca przerwania.
        wiadomosci.append({"role": "assistant", "content": o.get("content", [])})
    return czytaj_anthropic(odpowiedzi)


def czytaj_openai(o: dict) -> dict:
    """Responses API: tekst w output[type=message].content[type=output_text], cytowania w annotations."""
    w = wynik_pusty()
    w["model"] = o.get("model")
    teksty = []
    for el in o.get("output", []):
        if el.get("type") == "web_search_call":
            w["wyszukiwania"] += 1
            for z in ((el.get("action") or {}).get("sources") or []):
                if z.get("url"):
                    w["wyniki_wyszukiwania"].append({"url": z["url"], "tytul": z.get("title")})
        elif el.get("type") == "message":
            for c in el.get("content", []):
                if c.get("type") == "output_text":
                    teksty.append(c.get("text", ""))
                    for a in c.get("annotations") or []:
                        if a.get("type") == "url_citation" and a.get("url"):
                            w["zrodla"].append({"url": a["url"], "tytul": a.get("title")})
    u = o.get("usage") or {}
    w["tekst"] = "\n".join(teksty).strip()
    w["tokeny_we"], w["tokeny_wy"] = _liczba(u, "input_tokens"), _liczba(u, "output_tokens")
    return w


def zapytaj_openai(pytanie: str, cfg: dict, klucz: str) -> dict:
    cialo = {"model": cfg["model"], "input": pytanie, "tools": [{"type": "web_search"}], "store": False}
    return czytaj_openai(wyslij("https://api.openai.com/v1/responses",
                                {"Authorization": f"Bearer {klucz}"}, cialo))


def czytaj_gemini(o: dict) -> dict:
    """Interactions API z google_search: steps[type=model_output].content[].annotations (url_citation)."""
    w = wynik_pusty()
    w["model"] = o.get("model")
    teksty = []
    kroki = o.get("steps") or o.get("outputs") or []
    for krok in kroki:
        typ = krok.get("type")
        if typ == "google_search_call":
            w["wyszukiwania"] += max(1, len((krok.get("arguments") or {}).get("queries") or []))
        elif typ in ("model_output", "text"):
            tresci = krok.get("content") if typ == "model_output" else [krok]
            for c in tresci or []:
                if c.get("type") == "text":
                    teksty.append(c.get("text", ""))
                    for a in c.get("annotations") or []:
                        if a.get("url"):
                            w["zrodla"].append({"url": a["url"], "tytul": a.get("title")})
    u = o.get("usage") or o.get("usage_metadata") or {}
    w["tekst"] = "\n".join(teksty).strip()
    w["tokeny_we"] = _liczba(u, "total_input_tokens", "input_tokens", "prompt_token_count")
    w["tokeny_wy"] = _liczba(u, "total_output_tokens", "output_tokens", "candidates_token_count")
    return w


def zapytaj_gemini(pytanie: str, cfg: dict, klucz: str) -> dict:
    naglowki = {"x-goog-api-key": klucz, "Api-Revision": cfg.get("api_revision", "2026-05-20")}
    cialo = {"model": cfg["model"], "input": pytanie, "tools": [{"type": "google_search"}]}
    return czytaj_gemini(wyslij("https://generativelanguage.googleapis.com/v1beta/interactions",
                                naglowki, cialo))


def czytaj_perplexity(o: dict) -> dict:
    """Agent API: tekst w output[type=message], źródła w output[type=search_results].results,
    odwołania w tekście jako [1] albo [web:1] (numer = id wyniku)."""
    w = wynik_pusty()
    w["model"] = o.get("model")
    teksty, wyniki = [], {}
    for el in o.get("output", []):
        if el.get("type") == "search_results":
            w["wyszukiwania"] += max(1, len(el.get("queries") or []))
            for r in el.get("results") or []:
                if r.get("url"):
                    z = {"url": r["url"], "tytul": r.get("title")}
                    w["wyniki_wyszukiwania"].append(z)
                    wyniki[str(r.get("id"))] = z
        elif el.get("type") == "message":
            for c in el.get("content", []):
                if c.get("type") == "output_text":
                    teksty.append(c.get("text", ""))
                    for a in c.get("annotations") or []:
                        if a.get("url"):
                            w["zrodla"].append({"url": a["url"], "tytul": a.get("title")})
    w["tekst"] = "\n".join(teksty).strip()
    for nr in dict.fromkeys(re.findall(r"\[(?:web:)?(\d+)\]", w["tekst"])):
        if nr in wyniki and wyniki[nr] not in w["zrodla"]:
            w["zrodla"].append(wyniki[nr])
    u = o.get("usage") or {}
    w["tokeny_we"], w["tokeny_wy"] = _liczba(u, "input_tokens"), _liczba(u, "output_tokens")
    koszt = u.get("cost")
    if isinstance(koszt, dict) and isinstance(koszt.get("total_cost"), (int, float)):
        w["koszt_dostawcy_usd"] = float(koszt["total_cost"])
    return w


def zapytaj_perplexity(pytanie: str, cfg: dict, klucz: str) -> dict:
    cialo = {"model": cfg["model"], "input": pytanie, "tools": [{"type": "web_search"}]}
    return czytaj_perplexity(wyslij("https://api.perplexity.ai/v1/agent",
                                    {"Authorization": f"Bearer {klucz}"}, cialo))


ZAPYTAJ = {"anthropic": zapytaj_anthropic, "openai": zapytaj_openai,
           "gemini": zapytaj_gemini, "perplexity": zapytaj_perplexity}


def koszt(wynik: dict, cfg: dict) -> tuple[float, bool]:
    """Koszt zapytania w USD i czy to tylko szacunek (gdy dostawca nie podał liczby tokenów)."""
    if wynik.get("koszt_dostawcy_usd") is not None:
        return wynik["koszt_dostawcy_usd"], False
    if wynik.get("tokeny_we") is None or wynik.get("tokeny_wy") is None:
        return cfg["szacunek_usd_na_zapytanie"], True
    return (wynik["tokeny_we"] * cfg["cena_usd_za_1m_wejscie"] / 1e6
            + wynik["tokeny_wy"] * cfg["cena_usd_za_1m_wyjscie"] / 1e6
            + wynik.get("wyszukiwania", 0) * cfg["cena_usd_za_wyszukiwanie"]), False


# ---------------------------------------------------------------------------
# Plan, przebieg i raport
# ---------------------------------------------------------------------------

def wczytaj_dane(plik: Path = DANE) -> dict:
    return json.loads(plik.read_text(encoding="utf-8"))


def katalog_poza_repo(katalog: Path) -> Path:
    """Wyniki nie mogą trafić do repozytorium, bo całe repo jest publiczną stroną."""
    k = katalog.expanduser().resolve()
    if k == KORZEN or KORZEN in k.parents:
        sys.exit(f"Katalog wyników {k} leży w repozytorium strony, które jest publiczne. "
                 f"Podaj katalog poza nim, np. --wyniki {DOMYSLNE_WYNIKI}")
    return k


def plan(dane: dict, dostawcy: list[str], powtorzenia: int, filtr_pytan: list[str] | None) -> list[dict]:
    pytania = [p for p in dane["pytania"] if not filtr_pytan or p["id"] in filtr_pytan]
    return [{"dostawca": d, "pytanie": p, "powtorzenie": n}
            for d in dostawcy for p in pytania for n in range(1, powtorzenia + 1)]


def szacunek(zadania: list[dict], dane: dict) -> float:
    return sum(dane["dostawcy"][z["dostawca"]]["szacunek_usd_na_zapytanie"] for z in zadania)


def procent(licznik: int, mianownik: int) -> str:
    return f"{100 * licznik / mianownik:.0f}% ({licznik}/{mianownik})" if mianownik else "brak danych"


def podsumuj(rekordy: list[dict], gra: dict) -> dict:
    """Wskaźniki na dostawcę. Odpowiedzi z błędem nie wchodzą do mianownika."""
    wynik = {}
    for d in KOLEJNOSC_DOSTAWCOW:
        wlasne = [r for r in rekordy if r["dostawca"] == d]
        if not wlasne:
            continue
        dobre = [r for r in wlasne if not r.get("blad")]
        oceny = [ocen(r, gra) for r in dobre]
        zwykle = [o for r, o in zip(dobre, oceny) if r.get("scenariusz") != "bledna_nazwa"]
        bledne = [o for r, o in zip(dobre, oceny) if r.get("scenariusz") == "bledna_nazwa"]
        pozycje = [o["pozycja"] for o in zwykle if o["pozycja"]]
        n = len(zwykle)
        wynik[d] = {
            "modele": sorted({r.get("model") or r.get("model_zadany") or "?" for r in wlasne}),
            "odpowiedzi": n,
            "bledy": len(wlasne) - len(dobre),
            "wzmianki": sum(o["wzmianka"] for o in zwykle),
            "wzmianki_rozmyte": sum(o["rozmyta"] for o in zwykle),
            "cytowania": sum(o["cytowanie"] for o in zwykle),
            "w_wyszukiwaniu": sum(o["w_wyszukiwaniu"] for o in zwykle),
            "pozycje": pozycje,
            "srednia_pozycja": round(sum(pozycje) / len(pozycje), 1) if pozycje else None,
            "bledna_nazwa_odpowiedzi": len(bledne),
            "bledna_nazwa_rozpoznana": sum(o["wzmianka"] for o in bledne),
            "wzmianki_proc": round(100 * sum(o["wzmianka"] for o in zwykle) / n, 1) if n else None,
            "cytowania_proc": round(100 * sum(o["cytowanie"] for o in zwykle) / n, 1) if n else None,
            "koszt_usd": round(sum(r.get("koszt_usd") or 0 for r in wlasne), 4),
        }
    return wynik


def poprzedni_przebieg(katalog: Path) -> tuple[str, dict] | None:
    """Najnowszy wcześniejszy przebieg w tym samym katalogu wyników (po nazwie z datą)."""
    kandydaci = sorted(p for p in katalog.parent.iterdir()
                       if p.is_dir() and p.name < katalog.name and (p / PLIK_PODSUMOWANIA).exists())
    if not kandydaci:
        return None
    ost = kandydaci[-1]
    return ost.name, json.loads((ost / PLIK_PODSUMOWANIA).read_text(encoding="utf-8"))


def roznica(teraz: float | None, przedtem: float | None, jednostka: str = " pp") -> str:
    if teraz is None or przedtem is None:
        return "—"
    r = teraz - przedtem
    return f"{'+' if r > 0 else ''}{r:.1f}{jednostka}" if r else "bez zmian"


def wczytaj_rekordy(katalog: Path) -> list[dict]:
    plik = katalog / PLIK_ODPOWIEDZI
    if not plik.exists():
        sys.exit(f"Brak pliku {plik}")
    return [json.loads(l) for l in plik.read_text(encoding="utf-8").splitlines() if l.strip()]


def raport(katalog: Path, dane: dict) -> Path:
    """Tworzy raport Markdown, podsumowanie JSON (do porównań) i arkusz CSV do ręcznej oceny."""
    gra = dane["gra"]
    rekordy = wczytaj_rekordy(katalog)
    pods = podsumuj(rekordy, gra)
    pop = poprzedni_przebieg(katalog)
    (katalog / PLIK_PODSUMOWANIA).write_text(
        json.dumps({"przebieg": katalog.name, "dostawcy": pods}, ensure_ascii=False, indent=2), encoding="utf-8")

    L = [f"# Widoczność {gra['nazwa']} w czatach AI: przebieg {katalog.name}", ""]
    powt = max((r.get("powtorzenie", 1) for r in rekordy), default=1)
    L += [f"Raport pokazuje, jak często czaty AI z wyszukiwaniem w sieci wymieniają grę {gra['nazwa']} "
          f"i czy podają jako źródło {', '.join(gra['domeny'])}. Każde pytanie zadano bez kontekstu, "
          f"{powt} raz(y) u każdego dostawcy. Próbka jest mała, więc różnice o kilka punktów procentowych "
          f"między tygodniami nie muszą nic znaczyć. Łączny koszt (wyliczony z liczby tokenów, a gdy jej brak, "
          f"szacowany): {sum(r.get('koszt_usd') or 0 for r in rekordy):.2f} USD.", ""]
    L += ["## Słownik wskaźników", "",
          "- **Wzmianki**: odsetek odpowiedzi, które wymieniają nazwę gry (także zapis rozmyty, np. „River Fly Store”; "
          "takie trafienia są policzone osobno). Pytania z błędną nazwą nie wchodzą do tego wskaźnika.",
          "- **Cytowania**: odsetek odpowiedzi, w których czat podał stronę z domeny gry jako źródło (link przy odpowiedzi).",
          "- **W wynikach wyszukiwania**: odsetek odpowiedzi, w których wyszukiwarka czatu znalazła stronę z domeny gry, "
          "nawet jeśli czat jej potem nie zacytował. Nie każdy dostawca to zwraca.",
          "- **Średnia pozycja**: miejsce gry na liście w odpowiedzi (1 = pierwsza), liczone tylko tam, gdzie odpowiedź "
          "jest listą i gra na niej jest.",
          "- **Błędna nazwa**: pytania o „River Fly Fishing”. Rozpoznanie oznacza, że odpowiedź podała właściwą nazwę.",
          "- **Rekomendacja i poprawność informacji** wymagają oceny człowieka. Program ich nie zgaduje: "
          f"kolumny do wypełnienia są w pliku `{PLIK_OCENY}`.", ""]

    L += ["## Wyniki według dostawców", "",
          "| Dostawca | Model | Odpowiedzi | Wzmianki | Cytowania | W wynikach wyszukiwania | Średnia pozycja | Błędna nazwa rozpoznana | Błędy | Koszt USD |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for d, p in pods.items():
        rozmyte = f", w tym rozmyte {p['wzmianki_rozmyte']}" if p["wzmianki_rozmyte"] else ""
        L.append(f"| {NAZWY_DOSTAWCOW[d]} | {', '.join(p['modele'])} | {p['odpowiedzi']} | "
                 f"{procent(p['wzmianki'], p['odpowiedzi'])}{rozmyte} | {procent(p['cytowania'], p['odpowiedzi'])} | "
                 f"{procent(p['w_wyszukiwaniu'], p['odpowiedzi'])} | "
                 f"{p['srednia_pozycja'] if p['srednia_pozycja'] is not None else '—'} | "
                 f"{procent(p['bledna_nazwa_rozpoznana'], p['bledna_nazwa_odpowiedzi'])} | {p['bledy']} | "
                 f"{p['koszt_usd']:.2f} |")
    L.append("")

    L += ["## Porównanie z poprzednim przebiegiem", ""]
    if not pop:
        L += ["To pierwszy przebieg w tym katalogu wyników, więc nie ma z czym porównać.", ""]
    else:
        nazwa, stare = pop
        L += [f"Poprzedni przebieg: {nazwa}. Różnice w punktach procentowych (pp); dodatnia znaczy lepiej. "
              "Przy pozycji ujemna różnica znaczy wyżej na liście.", "",
              "| Dostawca | Wzmianki teraz | Zmiana | Cytowania teraz | Zmiana | Średnia pozycja | Zmiana |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for d, p in pods.items():
            s = stare.get("dostawcy", {}).get(d, {})
            L.append(f"| {NAZWY_DOSTAWCOW[d]} | {p['wzmianki_proc'] if p['wzmianki_proc'] is not None else '—'}% | "
                     f"{roznica(p['wzmianki_proc'], s.get('wzmianki_proc'))} | "
                     f"{p['cytowania_proc'] if p['cytowania_proc'] is not None else '—'}% | "
                     f"{roznica(p['cytowania_proc'], s.get('cytowania_proc'))} | "
                     f"{p['srednia_pozycja'] if p['srednia_pozycja'] is not None else '—'} | "
                     f"{roznica(p['srednia_pozycja'], s.get('srednia_pozycja'), '')} |")
        L.append("")

    L += ["## Wzmianki według pytań", "",
          "Liczba odpowiedzi z nazwą gry na liczbę odpowiedzi bez błędu.", ""]
    obecni = list(pods)
    L += ["| Pytanie | " + " | ".join(NAZWY_DOSTAWCOW[d] for d in obecni) + " |",
          "| --- |" + " --- |" * len(obecni)]
    for p in dane["pytania"]:
        komorki = []
        for d in obecni:
            rr = [r for r in rekordy if r["dostawca"] == d and r["pytanie_id"] == p["id"] and not r.get("blad")]
            komorki.append(f"{sum(ocen(r, gra)['wzmianka'] for r in rr)}/{len(rr)}" if rr else "—")
        if any(k != "—" for k in komorki):
            dopisek = " (błędna nazwa)" if p.get("scenariusz") == "bledna_nazwa" else ""
            L.append(f"| {p['tekst']}{dopisek} | " + " | ".join(komorki) + " |")
    L.append("")

    L += ["## Odpowiedzi z nazwą gry", "",
          "Wycinki do przeczytania przy ręcznej ocenie: czy czat poleca grę i czy pisze o niej prawdę.", ""]
    z_nazwa = [(r, ocen(r, gra)) for r in rekordy if not r.get("blad")]
    z_nazwa = [(r, o) for r, o in z_nazwa if o["wzmianka"]]
    if not z_nazwa:
        L += ["Żadna odpowiedź nie wymieniła gry.", ""]
    for r, o in z_nazwa:
        poz = f", pozycja {o['pozycja']}" if o["pozycja"] else ""
        cyt = ", cytuje domenę" if o["cytowanie"] else ""
        L += [f"- **{NAZWY_DOSTAWCOW[r['dostawca']]}**, „{r['pytanie']}” (powtórzenie {r['powtorzenie']}{poz}{cyt}): "
              f"{fragment(r['tekst'], gra)}"]
    L.append("")

    bledy = [r for r in rekordy if r.get("blad")]
    if bledy:
        L += ["## Błędy zapytań", ""]
        L += [f"- {NAZWY_DOSTAWCOW[r['dostawca']]}, „{r['pytanie']}”: {r['blad']}" for r in bledy]
        L.append("")
    plik = katalog / PLIK_RAPORTU
    plik.write_text("\n".join(L), encoding="utf-8")

    with open(katalog / PLIK_OCENY, "w", encoding="utf-8-sig", newline="") as f:
        zapis = csv.writer(f, delimiter=";")
        zapis.writerow(["dostawca", "model", "pytanie", "powtorzenie", "wzmianka", "pozycja", "cytowanie",
                        "fragment", "rekomendacja (tak/nie/neutralnie)", "poprawnosc (poprawna/bledy)", "uwagi"])
        for r, o in z_nazwa:
            zapis.writerow([r["dostawca"], r.get("model"), r["pytanie"], r["powtorzenie"],
                            "rozmyta" if o["rozmyta"] else "tak", o["pozycja"] or "",
                            "tak" if o["cytowanie"] else "nie", fragment(r["tekst"], gra), "", "", ""])
    return plik


def main(argv: list[str] | None = None) -> None:
    for strumien in (sys.stdout, sys.stderr):
        try:
            strumien.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--wyniki", type=Path, default=DOMYSLNE_WYNIKI,
                   help=f"katalog wyników poza repozytorium (domyślnie {DOMYSLNE_WYNIKI})")
    p.add_argument("--dostawcy", default=",".join(KOLEJNOSC_DOSTAWCOW),
                   help="lista po przecinku: anthropic,openai,gemini,perplexity")
    p.add_argument("--powtorzenia", type=int, default=3, help="ile razy zadać każde pytanie (domyślnie 3)")
    p.add_argument("--pytania", help="tylko te identyfikatory pytań, po przecinku")
    p.add_argument("--limit-usd", type=float, default=20.0,
                   help="przerwij, gdy szacowany lub naliczony koszt przekroczy tę kwotę (domyślnie 20)")
    p.add_argument("--limit-zapytan", type=int, default=250, help="najwięcej zapytań w przebiegu (domyślnie 250)")
    p.add_argument("--proba", action="store_true", help="pokaż plan i szacowany koszt, bez zapytań do API")
    p.add_argument("--raport", type=Path, metavar="KATALOG", help="tylko utwórz raport z zapisanego przebiegu")
    p.add_argument("--dane", type=Path, default=DANE, help=argparse.SUPPRESS)
    a = p.parse_args(argv)
    dane = wczytaj_dane(a.dane)

    if a.raport:
        print(f"Raport: {raport(katalog_poza_repo(a.raport), dane)}")
        return

    dostawcy = [d.strip() for d in a.dostawcy.split(",") if d.strip()]
    nieznani = [d for d in dostawcy if d not in dane["dostawcy"]]
    if nieznani:
        sys.exit(f"Nieznani dostawcy: {', '.join(nieznani)}. Dostępni: {', '.join(dane['dostawcy'])}")
    if a.powtorzenia < 1:
        sys.exit("--powtorzenia musi być co najmniej 1")
    klucze = {d: os.environ.get(dane["dostawcy"][d]["zmienna_klucza"], "").strip() for d in dostawcy}
    filtr = [x.strip() for x in a.pytania.split(",")] if a.pytania else None
    if filtr:
        brak = set(filtr) - {q["id"] for q in dane["pytania"]}
        if brak:
            sys.exit(f"Nie ma pytań o identyfikatorach: {', '.join(sorted(brak))}")
    wyniki = katalog_poza_repo(a.wyniki)

    print("Dostawcy:")
    for d in dostawcy:
        cfg = dane["dostawcy"][d]
        stan = "klucz jest" if klucze[d] else f"BRAK klucza w zmiennej {cfg['zmienna_klucza']}, pominięty"
        print(f"  {NAZWY_DOSTAWCOW[d]:20} model {cfg['model']:20} {stan}")
    aktywni = [d for d in dostawcy if klucze[d]]
    zadania = plan(dane, aktywni if not a.proba else dostawcy, a.powtorzenia, filtr)
    koszt_szac = szacunek(zadania, dane)

    if a.proba:
        print(f"\nTryb próbny: niczego nie wysyłam. Plan dla wszystkich wybranych dostawców "
              f"(także bez klucza), {a.powtorzenia} powtórzenia:")
        for d in dostawcy:
            n = sum(1 for z in zadania if z["dostawca"] == d)
            print(f"  {NAZWY_DOSTAWCOW[d]:20} {n:4} zapytań, około {n * dane['dostawcy'][d]['szacunek_usd_na_zapytanie']:.2f} USD")
        print(f"Razem {len(zadania)} zapytań, szacunkowo {koszt_szac:.2f} USD "
              f"(limit {a.limit_usd:.2f} USD i {a.limit_zapytan} zapytań).")
        tylko_z_kluczem = [z for z in zadania if klucze[z["dostawca"]]]
        print(f"Z obecnymi kluczami poszłoby {len(tylko_z_kluczem)} zapytań "
              f"(około {szacunek(tylko_z_kluczem, dane):.2f} USD).")
        if len(zadania) > a.limit_zapytan or koszt_szac > a.limit_usd:
            print("Uwaga: pełny plan przekracza limit. Zmniejsz --powtorzenia, wybierz --dostawcy albo podnieś limit.")
        print(f"Wyniki trafiłyby do {wyniki}")
        print("\nPytania:")
        for q in dane["pytania"]:
            if not filtr or q["id"] in filtr:
                print(f"  [{q['id']}] {q['tekst']}" + ("  (scenariusz: błędna nazwa)" if q.get("scenariusz") else ""))
        return

    if not aktywni:
        zmienne = ", ".join(dane["dostawcy"][d]["zmienna_klucza"] for d in dostawcy)
        sys.exit(f"Brak kluczy API. Ustaw co najmniej jedną zmienną środowiskową: {zmienne}. "
                 "Szczegóły w README, sekcja „Widoczność w czatach AI”.")
    if len(zadania) > a.limit_zapytan:
        sys.exit(f"Plan ma {len(zadania)} zapytań, a limit to {a.limit_zapytan}. Zmniejsz --powtorzenia "
                 "albo podnieś --limit-zapytan.")
    if koszt_szac > a.limit_usd:
        sys.exit(f"Szacowany koszt {koszt_szac:.2f} USD przekracza limit {a.limit_usd:.2f} USD. "
                 "Zmniejsz --powtorzenia, wybierz --dostawcy albo podnieś --limit-usd.")

    katalog = wyniki / datetime.now().strftime("%Y-%m-%d_%H%M%S")
    katalog.mkdir(parents=True, exist_ok=False)
    print(f"\n{len(zadania)} zapytań, szacunkowo {koszt_szac:.2f} USD. Wyniki: {katalog}")
    naliczone = 0.0
    with open(katalog / PLIK_ODPOWIEDZI, "a", encoding="utf-8") as plik:
        for i, z in enumerate(zadania, 1):
            d, q, cfg = z["dostawca"], z["pytanie"], dane["dostawcy"][z["dostawca"]]
            if naliczone >= a.limit_usd:
                print(f"Przerywam: naliczony koszt {naliczone:.2f} USD osiągnął limit {a.limit_usd:.2f} USD.")
                break
            print(f"[{i}/{len(zadania)}] {d}: {q['tekst']} (#{z['powtorzenie']})")
            start = time.time()
            rekord = {"data": datetime.now().astimezone().isoformat(timespec="seconds"),
                      "przebieg": katalog.name, "dostawca": d, "model_zadany": cfg["model"],
                      "pytanie_id": q["id"], "jezyk": q["jezyk"], "scenariusz": q.get("scenariusz"),
                      "pytanie": q["tekst"], "powtorzenie": z["powtorzenie"]}
            try:
                w = ZAPYTAJ[d](q["tekst"], cfg, klucze[d])
                k, szac = koszt(w, cfg)
                rekord.update({"model": w["model"] or cfg["model"], "tekst": w["tekst"], "zrodla": w["zrodla"],
                               "wyniki_wyszukiwania": w["wyniki_wyszukiwania"], "wyszukiwania": w["wyszukiwania"],
                               "tokeny_we": w["tokeny_we"], "tokeny_wy": w["tokeny_wy"],
                               "koszt_usd": round(k, 5), "koszt_szacowany": szac, "blad": None})
            except BladApi as e:
                print(f"    błąd: {e}")
                k = cfg["szacunek_usd_na_zapytanie"]
                rekord.update({"model": cfg["model"], "tekst": "", "zrodla": [], "wyniki_wyszukiwania": [],
                               "koszt_usd": 0.0, "koszt_szacowany": True, "blad": str(e)})
                # Błąd mógł zostać naliczony częściowo; do limitu liczymy ostrożnie pełny szacunek.
            naliczone += k
            rekord["czas_s"] = round(time.time() - start, 1)
            plik.write(json.dumps(rekord, ensure_ascii=False) + "\n")
            plik.flush()
    print(f"\nKoszt liczony do limitu (zapytania z błędem ostrożnie według szacunku): około {naliczone:.2f} USD.")
    print(f"Raport: {raport(katalog, dane)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Powiadamia wyszukiwarki (Bing, Yandex, Seznam i inne w IndexNow) o stronach z sitemap.xml.

Bing zasila wyszukiwanie w ChatGPT i Copilocie, więc po zmianie treści warto go powiadomić od razu,
zamiast czekać, aż robot sam wróci. Klucz jest publiczny z definicji: leży w pliku <klucz>.txt
w katalogu głównym strony, a IndexNow sprawdza go przed przyjęciem zgłoszenia.

Użycie (po scaleniu zmian do main i odświeżeniu GitHub Pages):
  python3 narzedzia/indexnow.py            wszystkie adresy z sitemap.xml
  python3 narzedzia/indexnow.py --od 2026-11-25   tylko strony z <lastmod> od tej daty
  python3 narzedzia/indexnow.py --proba    pokazuje listę, niczego nie wysyła
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

KORZEN = Path(__file__).resolve().parent.parent
ADRES = "https://arturbyrski.pl"
KLUCZ = "750996d55b19827dda883a485b7a8196"
PUNKT = "https://api.indexnow.org/indexnow"


def adresy(od: str | None) -> list[str]:
    mapa = (KORZEN / "sitemap.xml").read_text(encoding="utf-8")
    wynik = []
    for wpis in re.findall(r"<url>(.*?)</url>", mapa, re.S):
        loc = re.search(r"<loc>(.*?)</loc>", wpis).group(1)
        mod = re.search(r"<lastmod>(.*?)</lastmod>", wpis)
        if od and (not mod or mod.group(1) < od):
            continue
        wynik.append(loc)
    return wynik


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--od", help="tylko strony zmienione od tej daty (RRRR-MM-DD)")
    p.add_argument("--proba", action="store_true", help="tylko pokaż adresy")
    a = p.parse_args()
    lista = adresy(a.od)
    print(f"{len(lista)} adresów")
    if a.proba or not lista:
        print("\n".join(lista))
        return
    with urllib.request.urlopen(f"{ADRES}/{KLUCZ}.txt", timeout=20) as r:
        if r.read().decode().strip() != KLUCZ:
            sys.exit("Plik klucza na stronie nie zgadza się z KLUCZ. Najpierw scal zmiany i poczekaj na GitHub Pages.")
    dane = json.dumps({"host": "arturbyrski.pl", "key": KLUCZ,
                       "keyLocation": f"{ADRES}/{KLUCZ}.txt", "urlList": lista}).encode()
    zad = urllib.request.Request(PUNKT, data=dane, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(zad, timeout=30) as r:
        print(f"IndexNow odpowiedział {r.status}")


if __name__ == "__main__":
    main()

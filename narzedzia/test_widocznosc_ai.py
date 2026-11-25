"""Testy narzedzia/widocznosc_ai.py bez sieci: python3 -m unittest discover -s narzedzia -p "test_*.py"

Odpowiedzi czatów w testach są fikcyjne i skrócone; służą tylko do sprawdzenia wykrywania i odczytu formatów.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import widocznosc_ai as w  # noqa: E402

DANE = w.wczytaj_dane()
GRA = DANE["gra"]


class Wzmianki(unittest.TestCase):
    def test_zapisy_nazwy(self):
        for tekst in ["Polecam River Fly Shop.", "river fly shop", "RIVER-FLY-SHOP (PC)", "RiverFlyShop",
                      "gra „River Fly Shop” od polskiego twórcy", "River  Fly\nShop", "**River Fly Shop**"]:
            with self.subTest(tekst=tekst):
                wynik = w.wykryj_wzmianke(tekst, GRA)
                self.assertTrue(wynik["wzmianka"])
                self.assertFalse(wynik["rozmyta"])

    def test_bledna_nazwa_to_nie_wzmianka(self):
        for tekst in ["River Fly Fishing to gra...", "Fly Fishing Shop Simulator", "a river, fly shops nearby",
                      "deliver fly shop", "River Fly Shopping"]:
            with self.subTest(tekst=tekst):
                self.assertFalse(w.wykryj_wzmianke(tekst, GRA)["wzmianka"])

    def test_wariant_rozmyty(self):
        wynik = w.wykryj_wzmianke("Maybe you mean River Fly Store?", GRA)
        self.assertTrue(wynik["wzmianka"])
        self.assertTrue(wynik["rozmyta"])

    def test_tworca(self):
        self.assertTrue(w.wymienia_tworce("Gra Artura Byrskiego? Nie, Artur Byrski Link Technologies", GRA))
        self.assertFalse(w.wymienia_tworce("Artur Nowak", GRA))


class Cytowania(unittest.TestCase):
    domeny = ["arturbyrski.pl"]

    def test_hosty(self):
        self.assertTrue(w.host_z_domeny("https://arturbyrski.pl/gry/river-fly-shop/", self.domeny))
        self.assertTrue(w.host_z_domeny("https://www.arturbyrski.pl/en/", self.domeny))
        self.assertTrue(w.host_z_domeny("arturbyrski.pl", self.domeny))
        self.assertFalse(w.host_z_domeny("https://notarturbyrski.pl/", self.domeny))
        self.assertFalse(w.host_z_domeny("https://example.com/?u=arturbyrski.pl", self.domeny))
        self.assertFalse(w.host_z_domeny("", self.domeny))

    def test_przekierowanie_gemini_z_tytulem_domeny(self):
        z = {"url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc", "tytul": "arturbyrski.pl"}
        self.assertTrue(w.zrodlo_z_domeny(z, self.domeny))
        z["tytul"] = "River Fly Shop – arturbyrski.pl recenzja"
        self.assertFalse(w.zrodlo_z_domeny(z, self.domeny))

    def test_cytowanie_wyszukiwanie_tekst(self):
        r = {"tekst": "Więcej na arturbyrski.pl.", "zrodla": [{"url": "https://store.steampowered.com/"}],
             "wyniki_wyszukiwania": [{"url": "https://arturbyrski.pl/en/games/river-fly-shop/"}]}
        c = w.wykryj_cytowanie(r, self.domeny)
        self.assertEqual(c, {"cytowanie": False, "w_wyszukiwaniu": True, "domena_w_tekscie": True})


class Pozycja(unittest.TestCase):
    def test_lista_numerowana(self):
        t = "Najlepsze gry:\n1. Fly Fishing Sim\n2. Ultimate Fishing\n3. River Fly Shop – sklep\n"
        self.assertEqual(w.pozycja_na_liscie(t, GRA), 3)

    def test_numer_pogrubiony(self):
        self.assertEqual(w.pozycja_na_liscie("**1. Gra A**\n**2. River Fly Shop**", GRA), 2)

    def test_punktory_z_podpunktami(self):
        t = ("- Fly Fishing Sim\n  - realistyczne rzuty\n  - wiele łowisk\n"
             "- Call of the Wild Angler\n- River Fly Shop\n")
        self.assertEqual(w.pozycja_na_liscie(t, GRA), 3)

    def test_naglowki_tego_samego_poziomu(self):
        t = "## Gry wędkarskie\n### Gra A\nopis\n### Gra B\n- cecha\n### River Fly Shop\nopis"
        self.assertEqual(w.pozycja_na_liscie(t, GRA), 3)

    def test_bez_listy(self):
        self.assertIsNone(w.pozycja_na_liscie("Warto spojrzeć na River Fly Shop, grę w produkcji.", GRA))
        self.assertIsNone(w.pozycja_na_liscie("1. Gra A\n2. Gra B", GRA))


class Formaty(unittest.TestCase):
    """Odczyt odpowiedzi w kształcie z dokumentacji dostawców (2026-11), bez wywołań API."""

    def test_anthropic_z_pause_turn(self):
        o1 = {"model": "claude-opus-5-5", "stop_reason": "pause_turn", "content": [
            {"type": "server_tool_use", "name": "web_search"},
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "url": "https://arturbyrski.pl/gry/river-fly-shop/", "title": "RFS"}]},
            {"type": "text", "text": "Oto lista:\n"}],
            "usage": {"input_tokens": 1000, "output_tokens": 50, "server_tool_use": {"web_search_requests": 1}}}
        o2 = {"model": "claude-opus-5-5", "stop_reason": "end_turn", "content": [
            {"type": "text", "text": "1. River Fly Shop", "citations": [
                {"type": "web_search_result_location", "url": "https://arturbyrski.pl/gry/river-fly-shop/",
                 "title": "RFS", "cited_text": "..."}]}],
            "usage": {"input_tokens": 500, "output_tokens": 20}}
        r = w.czytaj_anthropic([o1, o2])
        self.assertEqual(r["tekst"], "Oto lista:\n1. River Fly Shop")
        self.assertEqual(r["zrodla"][0]["url"], "https://arturbyrski.pl/gry/river-fly-shop/")
        self.assertEqual(len(r["wyniki_wyszukiwania"]), 1)
        self.assertEqual((r["tokeny_we"], r["tokeny_wy"], r["wyszukiwania"]), (1500, 70, 1))

    def test_openai(self):
        o = {"model": "gpt-6.2-astra", "output": [
            {"type": "web_search_call", "status": "completed", "action": {"type": "search", "query": "x"}},
            {"type": "message", "content": [{"type": "output_text", "text": "Try River Fly Shop.", "annotations": [
                {"type": "url_citation", "url": "https://arturbyrski.pl/en/games/river-fly-shop/",
                 "title": "River Fly Shop", "start_index": 0, "end_index": 5}]}]}],
            "usage": {"input_tokens": 3000, "output_tokens": 200}}
        r = w.czytaj_openai(o)
        self.assertEqual(r["tekst"], "Try River Fly Shop.")
        self.assertEqual(r["wyszukiwania"], 1)
        self.assertTrue(w.wykryj_cytowanie(r, ["arturbyrski.pl"])["cytowanie"])

    def test_gemini(self):
        o = {"model": "gemini-4-hydrogen", "steps": [
            {"type": "thought", "summary": []},
            {"type": "google_search_call", "arguments": {"queries": ["fly fishing game", "fly shop game"]}},
            {"type": "google_search_result", "call_id": "1", "result": [{"search_suggestions": "<div/>"}]},
            {"type": "model_output", "content": [{"type": "text", "text": "River Fly Shop", "annotations": [
                {"type": "url_citation", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/x",
                 "title": "arturbyrski.pl", "start_index": 0, "end_index": 14}]}]}]}
        r = w.czytaj_gemini(o)
        self.assertEqual(r["wyszukiwania"], 2)
        self.assertIsNone(r["tokeny_we"])
        self.assertTrue(w.wykryj_cytowanie(r, ["arturbyrski.pl"])["cytowanie"])

    def test_perplexity_odwolania(self):
        o = {"model": "perplexity/sonar", "output": [
            {"type": "search_results", "queries": ["q"], "results": [
                {"id": 1, "url": "https://store.steampowered.com/app/1", "title": "Steam"},
                {"id": 2, "url": "https://arturbyrski.pl/gry/river-fly-shop/", "title": "RFS"}]},
            {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": "River Fly Shop to gra w produkcji [web:2].", "annotations": []}]}],
            "usage": {"input_tokens": 100, "output_tokens": 40, "cost": {"total_cost": 0.0031}}}
        r = w.czytaj_perplexity(o)
        self.assertEqual([z["url"] for z in r["zrodla"]], ["https://arturbyrski.pl/gry/river-fly-shop/"])
        self.assertEqual(len(r["wyniki_wyszukiwania"]), 2)
        self.assertEqual(w.koszt(r, DANE["dostawcy"]["perplexity"]), (0.0031, False))

    def test_koszt_z_tokenow_i_szacunek(self):
        cfg = DANE["dostawcy"]["anthropic"]
        k, szac = w.koszt({"tokeny_we": 1_000_000, "tokeny_wy": 0, "wyszukiwania": 2}, cfg)
        self.assertFalse(szac)
        self.assertAlmostEqual(k, cfg["cena_usd_za_1m_wejscie"] + 2 * cfg["cena_usd_za_wyszukiwanie"])
        self.assertEqual(w.koszt({"tokeny_we": None, "tokeny_wy": None}, cfg),
                         (cfg["szacunek_usd_na_zapytanie"], True))


class PlanIRaport(unittest.TestCase):
    def test_dane_kompletne(self):
        ids = [p["id"] for p in DANE["pytania"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(p.get("scenariusz") == "bledna_nazwa" for p in DANE["pytania"]))
        for d in w.KOLEJNOSC_DOSTAWCOW:
            self.assertIn(d, DANE["dostawcy"])

    def test_plan_i_szacunek(self):
        z = w.plan(DANE, ["perplexity", "gemini"], 3, None)
        self.assertEqual(len(z), 2 * 3 * len(DANE["pytania"]))
        self.assertGreater(w.szacunek(z, DANE), 0)
        self.assertEqual(len(w.plan(DANE, ["openai"], 1, ["en-cozy"])), 1)

    def test_wyniki_w_repo_odrzucone(self):
        with self.assertRaises(SystemExit):
            w.katalog_poza_repo(w.KORZEN / "wyniki")
        with self.assertRaises(SystemExit):
            w.katalog_poza_repo(w.KORZEN)

    def test_proba_bez_kluczy_nie_wysyla(self):
        with tempfile.TemporaryDirectory() as tmp:
            w.main(["--proba", "--wyniki", tmp])  # brak wyjątku i brak sieci
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_raport_i_porownanie(self):
        def rek(d, pid, tekst, zrodla=(), scen=None, blad=None):
            return {"dostawca": d, "pytanie_id": pid, "pytanie": pid, "powtorzenie": 1, "scenariusz": scen,
                    "model": "m", "tekst": tekst, "zrodla": [{"url": u} for u in zrodla],
                    "wyniki_wyszukiwania": [], "koszt_usd": 0.01, "blad": blad}

        with tempfile.TemporaryDirectory() as tmp:
            stary, nowy = Path(tmp) / "2026-11-01_080000", Path(tmp) / "2026-11-08_080000"
            for k, rekordy in [
                (stary, [rek("openai", "en-cozy", "Stardew Valley"), rek("openai", "en-best-pc", "Nothing")]),
                (nowy, [rek("openai", "en-cozy", "1. A\n2. River Fly Shop", ["https://arturbyrski.pl/"]),
                        rek("openai", "en-best-pc", "Nothing"),
                        rek("openai", "en-bledna-nazwa", "Did you mean River Fly Shop?", scen="bledna_nazwa"),
                        rek("openai", "en-upcoming", "", blad="HTTP 500")])]:
                k.mkdir()
                (k / w.PLIK_ODPOWIEDZI).write_text(
                    "\n".join(json.dumps(r) for r in rekordy), encoding="utf-8")
                w.raport(k, DANE)
            pods = json.loads((nowy / w.PLIK_PODSUMOWANIA).read_text(encoding="utf-8"))["dostawcy"]["openai"]
            self.assertEqual((pods["odpowiedzi"], pods["wzmianki"], pods["cytowania"], pods["bledy"]), (2, 1, 1, 1))
            self.assertEqual(pods["srednia_pozycja"], 2)
            self.assertEqual((pods["bledna_nazwa_rozpoznana"], pods["bledna_nazwa_odpowiedzi"]), (1, 1))
            md = (nowy / w.PLIK_RAPORTU).read_text(encoding="utf-8")
            self.assertIn("Poprzedni przebieg: 2026-11-01_080000", md)
            self.assertIn("+50.0 pp", md)
            csv = (nowy / w.PLIK_OCENY).read_text(encoding="utf-8-sig")
            self.assertIn("rekomendacja", csv)


if __name__ == "__main__":
    unittest.main()

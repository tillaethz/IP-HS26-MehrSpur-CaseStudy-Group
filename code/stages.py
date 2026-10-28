"""
stages.py
=========
Infrastructure stage specifications for the Mobility Hub Forch project.
Paket A: Bahnhofraum, Umsteigekante, Wege, Tempo 30, 400 Veloplätze.
Paket B: Bus Forch–Glattal 15'-Takt, Anschlusssicherung, Busbevorzugung. Combined: A + B.
 
A 'stage' captures the physical infrastructure and operational interventions
that modify the multimodal transport network and skims in the Canton Zürich FSM model.
 
HOW TO USE
----------
Edit the two named packages below to define physical interventions and their
spatial scope. Each package groups railway improvements, mobility hubs and
appraisal assumptions (CAPEX, construction emissions and asset lifetime).
Baseline headway, technology and capacity assumptions stay in parameters.py;
deployment timing and triggers stay in adaptive_planning.py.
ASCs/betas describe common behavior, not automatic benefits of individual hubs.
Asset lifetimes below affect final-year appraisal only, not transport.
 
SURROGATE CONSEQUENCE
---------------------
The two packages can operate independently. Transport states are 0 (baseline),
1 (stations), 2 (tunnel), and 3 (both). The combined state contains the two
packages' benefits once each plus COMBINED_EFFECTS. One GP learns all four configurations. Changes
to their physical effects require rebuilding the surrogate and response table.
Changing only plan timing, costs, comfort capacity, construction emissions or
asset lifetimes does not require a surrogate rebuild. Rerun appraisal to include them.
 
--- CHEAT SHEET: PARAMETERS & INTERVENTIONS ---
 
1. Defining Spatial Scopes
   Interventions are targeted geographically using spatial filters:
   
   - "area_pairs": Selects OD skim cells between origins and destinations, not physical links.
     Filter by "municipality_name" (e.g. "Dietikon") or "city_quartier" (e.g. "Altstetten").
     Example: Reducing rail travel time between Zürich and Winterthur:
       "railway_expansions": [
           {
               "name": "Corridor Rail Upgrade",
               "area_pairs": [
                   {"origin": {"municipality_name": "Zürich"}, "destination": {"municipality_name": "Winterthur"}}
               ],
               "both_directions": True,
               "effects": {
                   "travel_time_reduction_pct": 15.0
               }
           }
       ]
   
   - "zones": Used for area-wide or zone-based interventions (e.g., station access, local networks).
     Filter by specific zone IDs or whole municipality names. The model selects
     the first two candidate stops per zone for walk and bicycle access, then
     applies effects to journeys using those stops.
     Example: Improving PT access & egress times in Dietlikon:
       "mobility_hubs": [
           {
               "name": "Dietlikon Hub Area",
               "zones": [{"municipality_name": "Dietlikon"}],  # or zone IDs: ["15401012"]
               "effects": {
                   "access_time_reduction_pct": 20.0,
                   "egress_time_reduction_pct": 20.0
               }
           }
       ]
 
 
2. Mode-Specific Physical Interventions
   Effects are defined under specific mode keys which target different transport networks:
   - "railway_expansions": A list of railway interventions. The section/service
     entry sets minutes saved, headway reduction and added comfort capacity.
     Additional entries can use OD filters and percentage "effects" as above.
   - "bike_highways": Modifies the Bicycle network.
   - "road_capacity": Modifies selected directed links in the local MSA road network.
   - "mobility_hubs": Modifies PT access, egress and transfer times for walk and bicycle access.
   - "section_time_saving_min" in a "railway_expansions" entry, or directly in a
     package: Minutes saved on the selected parameters.SECTION. For bike_route,
     enter the saving for the complete route; each journey receives the fraction
     corresponding to the improved route length it uses. A pt_stop instead uses
     station-specific mobility_hubs effects below.
     Savings are relative to baseline: stations save 1 minute, the tunnel 4,
     and both packages 6, including a 1-minute combined bonus. The optional external cohort receives the same saving
     in appraisal, without entering mode choice or assignment.
     Section settings follow parameters.SECTION; headway settings apply between
     corridor municipalities. OD filters on additional entries scope only their
     percentage "effects". Comfort capacity is used in crowding appraisal.
 
   Within these keys, you can apply effects like:
   - "travel_time_reduction_pct" (Reduces in-vehicle travel time)
   - "speed_increase_pct" (Increases average speed)
   - "distance_reduction_pct" (Reduces trip distance, e.g., a new tunnel or bridge)
   - "access_time_reduction_pct", "egress_time_reduction_pct" (Reduces walk time to/from PT)
   
   EXAMPLE 1: Road intervention (increasing selected link capacity by 25%)
   "road_capacity": [
       {
           # Find these directional IDs with the link editor in Notebook 02.
           "edge_ids": ["OSM_123456_789012_0", "OSM_789012_123456_0"],
           "effects": {"capacity_increase_pct": 25.0}
       }
   ]
 
   Road capacity is link-based: ``area_pairs`` select OD skim cells and cannot
   identify physical road links. The transport interface applies these edits
   to a copy of the corridor immediately before MSA assignment.
 
   EXAMPLE 2: Station Access Intervention (Reducing PT access/egress times by 20%)
   "mobility_hubs": [
       {
           "zones": [{"municipality_name": "Dietlikon"}],
           "effects": {"access_time_reduction_pct": 20.0, "egress_time_reduction_pct": 20.0}
       }
   ]
 
   EXAMPLE 3: Bike Intervention (Shortening bike travel distance by 15% via a direct cycle path/bridge)
   "bike_highways": [
       {
           "area_pairs": [{"origin": {"city_quartier": "Altstetten"}, "destination": {"municipality_name": "Dietikon"}}],
           "both_directions": True,
           "effects": {
               "distance_reduction_pct": 15.0,
               "speed_increase_pct": 10.0
           }
       }
   ]
 
   For a counted cycling route configured in parameters.SECTION, a package can
   instead set "section_time_saving_min": 2.0 directly. Do not also apply an OD
   time reduction for the same improvement.
 
   EXAMPLE 4: A specific station (rather than a municipality-wide access package)
   "mobility_hubs": [
       {"station": "Wallisellen", "effects": {
           "access_time_reduction_pct": 25.0,
           "egress_time_reduction_pct": 20.0,
           "transfer_time_reduction_pct": 15.0
       }}
   ]
   Access and egress affect their respective station users. Transfer reductions
   affect only represented physical walking at this station, not through users.
"""
 
from __future__ import annotations
from copy import deepcopy
import itertools
from math import isfinite
 
# =============================================================================
# 0. SPATIAL SELECTORS – MOBILITY HUB FORCH
# =============================================================================
# FSM-Zonen-IDs (grid_id). NICHT "municipality_name": "Küsnacht" verwenden – das würde
# auch den Bahnhof Küsnacht am See (S6/S16) treffen.
ZONE_FORCH = "15401012"     # Forch (Küsnacht) – Bahnhof
ZONE_AESCH = "19501005"     # Aesch (Maur)
ZONE_SCHEUREN = "19501006"  # Scheuren (Maur)
FORCH_HUB_ZONES = [ZONE_FORCH, ZONE_AESCH, ZONE_SCHEUREN]  # Einzugsgebiet (für Bericht/Karten)
 
# Bus 706 (VBZ, in den Baseline-Skims enthalten): Forch Bahnhof – Aesch – Ebmatingen
#   – Binz – Benglen – Fällanden – Schwerzenbach Bahnhof, heute 30'-Takt (2 Busse).
GLATTAL_BUS_DESTINATIONS = ["Fällanden", "Schwerzenbach"]
 
# WER NUTZT IM MODELL WELCHE ROUTE? (Skim-Check v2, Stage 0, häufigste Haltestellen)
#   Forch    -> Glattal: steigt in Forch direkt in Bus 706 ein (Halt 8590613), 0 Umstiege
#   Aesch    -> Glattal: steigt in AESCH direkt in Bus 706 ein (Halt 8590487), 0 Umstiege,
#                        Startwartezeit 15.0 min = 30'-Takt / 2
#   Scheuren -> Glattal: S18 ab Scheuren (8503064), Umstieg in Forch auf den Bus
#   Zumikon  -> Fällanden: S18 ab Zumikon (8503066), Umstieg in Forch auf den Bus
#   Zumikon  -> Schwerzenbach: Ausstieg am BAHNHOF Schwerzenbach (8503127) = S-Bahn via
#                        Zürich/Stettbach, NICHT via Forch -> Busmassnahmen wirken nicht
#   Egg      -> Glattal: S18 ab Egg (8503063), Umstieg in Forch auf den Bus
#   1 von 4 Zumikon-Zonen hat keinen ÖV-Zugang (Wert 999 = "keine Verbindung").
DIREKT_BUS = {          # Einstieg direkt in den Bus -> Startwartezeit
    "Forch": {"grid_id": [ZONE_FORCH]},
    "Aesch": {"grid_id": [ZONE_AESCH]},
}
UMSTEIGER_IN_FORCH = {  # S18 bis Forch, dort Umstieg auf den Bus -> Umsteigewartezeit
    "Scheuren": {"grid_id": [ZONE_SCHEUREN]},
    "Zumikon": {"municipality_name": "Zumikon"},
    "Egg": {"municipality_name": "Egg"},
}
 
 
# =============================================================================
# 0b. GRUNDLAGEN FÜR DIE PROZENTWERTE
# =============================================================================
# Alle %-Werte werden aus heutigen Skim-Werten (Skim-Check v2, Median über gültige
# Zonenpaare, pt_walk, Minuten) und einer Zielzeit berechnet:
#     Prozent = (1 - Zeit neu / Zeit heute) * 100      (Modell erlaubt 0 <= % < 100)
# Nur Relationen, deren Route im Modell über den Bus 706 / Forch läuft (siehe oben).
SKIM_HEUTE = {
    ("Forch", "Fällanden"):        {"ivt": 14.0, "initial_wait": 6.7,  "transfer_physical": 0.0, "transfer_wait": 0.0},
    ("Forch", "Schwerzenbach"):    {"ivt": 19.0, "initial_wait": 6.7,  "transfer_physical": 0.0, "transfer_wait": 0.0},
    ("Aesch", "Fällanden"):        {"ivt": 10.0, "initial_wait": 15.0, "transfer_physical": 0.0, "transfer_wait": 0.0},
    ("Aesch", "Schwerzenbach"):    {"ivt": 15.0, "initial_wait": 15.0, "transfer_physical": 0.0, "transfer_wait": 0.0},
    ("Scheuren", "Fällanden"):     {"ivt": 17.0, "initial_wait": 3.3,  "transfer_physical": 2.0, "transfer_wait": 6.7},
    ("Scheuren", "Schwerzenbach"): {"ivt": 22.0, "initial_wait": 3.3,  "transfer_physical": 2.0, "transfer_wait": 6.7},
    ("Zumikon", "Fällanden"):      {"ivt": 18.0, "initial_wait": 3.6,  "transfer_physical": 2.0, "transfer_wait": 6.7},
    # ("Zumikon", "Schwerzenbach") fehlt bewusst: Route via Zürich, nicht via Forch.
    ("Egg", "Fällanden"):          {"ivt": 22.0, "initial_wait": 3.6,  "transfer_physical": 2.0, "transfer_wait": 6.7},
    ("Egg", "Schwerzenbach"):      {"ivt": 25.0, "initial_wait": 3.6,  "transfer_physical": 2.0, "transfer_wait": 6.7},
}
 
 
def _pct(neu: float, heute: float) -> float:
    """Reduktion in %, damit der heutige Wert zum neuen Wert wird (0 <= % <= 99)."""
    if heute <= 0:
        return 0.0
    return round(min(99.0, max(0.0, 100.0 * (1.0 - neu / heute))), 1)
 
 
# --- A1: Bus-Bahn-Umsteigekante ---------------------------------------------
# Heute: Umsteigeweg S18 -> Bus 706 in Forch = 2.0 min (Skim, Median Scheuren/Zumikon/Egg;
#   Weg über den Bahnhofplatz inkl. Querung).
# Neu: Bushalt direkt neben dem Perron, ca. 30 m ebener Weg bei 1.2 m/s Gehgeschwindigkeit
#   = 25 s ≈ 0.5 min (inkl. Puffer).
UMSTEIGEWEG_HEUTE_MIN = 2.0
UMSTEIGEWEG_NEU_MIN = 0.5
A1_TRANSFER_TIME_PCT = _pct(UMSTEIGEWEG_NEU_MIN, UMSTEIGEWEG_HEUTE_MIN)   # = 75.0 %
 
# --- A2: Direkte Fuss-/Velowege + Velostation am Perron ------------------------
# Zugangszeit heute ab Zone Forch 20.3 min (Skim): der Weg führt über Umwege
#   (Strassennetz, Querungen). Umwegfaktor = Weglänge im Netz / Luftlinie.
#   Heute ~1.4 (typisch für ländliche, strassengebundene Netze), neu ~1.15 dank
#   direkter Wege und Velostation am Perron.
# Aesch und Scheuren nutzen im Modell ihre EIGENEN Haltestellen (Bus in Aesch, S18 in
#   Scheuren) -> neue Wege von dort zum Bahnhof Forch wirken im Modell nicht (qualitativ).
UMWEGFAKTOR_HEUTE = 1.40
UMWEGFAKTOR_NEU = 1.15
A2_ACCESS_EGRESS_PCT = _pct(UMWEGFAKTOR_NEU, UMWEGFAKTOR_HEUTE)          # = 17.9 %
 
# --- A3: Forchstrasse Tempo 30 im Bahnhofbereich -------------------------------
# Tempo 50 -> 30 auf den Strassenabschnitten am Bahnhofsraum (5 Abschnitte, beide
#   Richtungen, aus dem Editor 3.2), plus gesicherte Fussgängerquerung zum Platz.
#   Auto wird leicht langsamer (z. B. 260 m: 31 s statt 19 s). Kapazität unverändert.
FORCHSTRASSE_TEMPO30 = [
    {
        "name": "Forchstrasse Tempo 30 Bahnhofsraum",
        "edge_ids": [
            "OSM_1599383172_217302787_0",
            "OSM_1599383172_35924032_0",
            "OSM_217302787_1599383172_0",
            "OSM_217302787_7126219560_0",
            "OSM_35924029_35924032_0",
            "OSM_35924029_447936422_0",
            "OSM_35924032_1599383172_0",
            "OSM_35924032_35924029_0",
            "OSM_447936422_35924029_0",
            "OSM_7126219560_217302787_0",
        ],
        "effects": {"speed_kph": 30.0},
    },
]
 
# --- Paket B Basis: 2. Buslinie, 15'-Takt --------------------------------------
# Heute: Bus 706 mit 2 Bussen im 30'-Takt. Neu: + 2. Linie mit 2 Bussen, versetzt
#   -> 4 Busse, 15'-Takt Forch – Glattal.
# Mittlere Wartezeit ist proportional zum Takt (gleiche Logik wie die Modellfunktion
#   "Corridor service frequency"): Reduktion = 1 - 15/30.
#   Kontrolle Aesch: Skim-Startwartezeit 15.0 min = 30/2 -> neu 7.5 min. Passt.
BUS_TAKT_HEUTE_MIN = 30.0
BUS_TAKT_NEU_MIN = 15.0
B_INITIAL_WAIT_PCT = _pct(BUS_TAKT_NEU_MIN, BUS_TAKT_HEUTE_MIN)            # = 50.0 %
 
# --- B1: Anschlusssicherung S18 <-> Bus in Forch -------------------------------
# Heute: Umsteigewartezeit in Forch 6.7 min (Skim, Scheuren/Zumikon/Egg).
# Neu: Busfahrplan auf die S18 abgestimmt (Bus fährt kurz nach Ankunft der S18 ab,
#   wartet bei Verspätung). Zielwert 2 min = Anschlusspuffer.
#   Ersetzt den reinen Takteffekt beim Umsteigen (nicht zusätzlich).
UMSTEIGEWARTEZEIT_NEU_MIN = 2.0
 
# --- B3: Busbevorzugung Forch – Aesch – Ebmatingen -------------------------------
# Lichtsignal-Priorisierung an den Knoten + kurze Busspur vor dem Knoten Forch.
# Annahme: 1.5 min Zeitgewinn pro Fahrt ab Forch (0.5 min Knoten Forch + 1.0 min
#   Aesch – Ebmatingen). Wer in Aesch einsteigt, profitiert nur vom zweiten Teil (1.0 min).
#   Literatur zu Transit Signal Priority nennt 2–18 % Fahrzeitgewinn (u. a. US DOT
#   ITS JPO); 1–1.5 min auf 10–25 min liegt mit 4–11 % in diesem Bereich.
#   PRÜFEN: Anzahl Lichtsignale/Knoten auf der Route im Bericht nennen.
BUS_ZEITGEWINN_MIN = {"Forch": 1.5, "Aesch": 1.0}
BUS_ZEITGEWINN_UMSTEIGER_MIN = 1.5  # Umsteiger fahren ab Forch
 
 
def _bus_entries() -> list[dict]:
    """railway_expansions für Paket B, pro Relation aus SKIM_HEUTE berechnet."""
    entries = []
    for (von, nach), heute in SKIM_HEUTE.items():
        ziel = {"municipality_name": nach}
        if von in DIREKT_BUS:
            # Einstieg direkt in den Bus: 15'-Takt (Startwartezeit) + Busbevorzugung.
            gewinn = BUS_ZEITGEWINN_MIN[von]
            name = f"Bus 15'-Takt + Busbevorzugung: {von} – {nach}"
            origin = DIREKT_BUS[von]
            effects = {"initial_wait_reduction_pct": B_INITIAL_WAIT_PCT}
        else:
            # Umstieg S18 -> Bus in Forch: Anschlusssicherung + Busbevorzugung.
            gewinn = BUS_ZEITGEWINN_UMSTEIGER_MIN
            name = f"Anschluss S18 -> Bus + Busbevorzugung: {von} – {nach}"
            origin = UMSTEIGER_IN_FORCH[von]
            effects = {"transfer_wait_reduction_pct":
                       _pct(UMSTEIGEWARTEZEIT_NEU_MIN, heute["transfer_wait"])}
        # ivt enthält bei Umsteigern auch die S18-Fahrt -> Gewinn nur auf dem Busteil.
        effects["travel_time_reduction_pct"] = _pct(heute["ivt"] - gewinn, heute["ivt"])
        entries.append({
            "name": name,
            "area_pairs": [{"origin": origin, "destination": ziel}],
            "both_directions": True,
            "effects": effects,
        })
    return entries
 
 
# Resultierende Werte (zur Kontrolle, Stand Skim-Check v2):
#   A1 transfer_time                         75.0 %  (2.0 -> 0.5 min)
#   A2 access/egress                         17.9 %  (Umwegfaktor 1.40 -> 1.15)
#   B  initial_wait Forch/Aesch              50.0 %  (Takt 30' -> 15')
#   B1 transfer_wait Scheuren/Zumikon/Egg    70.1 %  (6.7 -> 2.0 min)
#   B3 travel_time: Forch–F 10.7, Forch–S 7.9, Aesch–F 10.0, Aesch–S 6.7,
#      Scheuren–F 8.8, Scheuren–S 6.8, Zumikon–F 8.3, Egg–F 6.8, Egg–S 6.0 %
 
 
# =============================================================================
# 1. PACKAGES: MOBILITY HUB FORCH
# =============================================================================
# Die Schlüssel "stations" und "tunnel" sind fixe technische Namen (der Plan-Code in
# adaptive_planning.py greift darauf zu) – NICHT umbenennen. Für Forch bedeuten sie:
#   "stations" -> Paket A: Bahnhofraum & Zugang      (Konfiguration 1)
#   "tunnel"   -> Paket B: Busangebot Glattal         (Konfiguration 2)
#   beide      -> Paket A + B, ohne Kombi-Bonus        (Konfiguration 3)
# Beide Pakete funktionieren unabhängig: A verbessert Hub und Zugang für die bestehende
# S18 und den bestehenden Bus 706; B verdichtet den Bus auch ohne Umbau des Platzes.
 
PACKAGES = {
    # -------------------------------------------------------------------------
    # PAKET A – Bahnhofraum, Umsteigekante, Wege, Tempo 30 & 400 Veloplätze ("stations")
    # -------------------------------------------------------------------------
    # Physisch:
    #   - Tiefgarage 150 PP; oberirdische P+R-Plätze aufgehoben (Zufahrt Kaltensteinstrasse)
    #   - Platz "Bahnhofraum Mitte" (3'800 m2) als Umsteige- und Aufenthaltsort
    #   - A1: Bushalt (Bus 706) direkt neben dem Forchbahn-Perron, ohne Strassenquerung
    #   - A2: direkte Fuss-/Velowege Aesch/Scheuren -> Bahnhof (~1 km), Velostation
    #         mit 400 Plätzen am Perron (überdacht, Teil abschliessbar, E-Bike-Laden)
    #   - A3: Forchstrasse Tempo 30 im Bahnhofbereich, gesicherte Querung
    # Im Modell:
    #   - mobility_hubs (Zone Forch): Zugang/Abgang -17.9 %, Umsteigeweg -75.0 %
    #   - road_capacity: Tempo 30 auf 5 Abschnitten am Bahnhofsraum (beide Richtungen)
    # Nicht im Modell (qualitativ beschreiben):
    #   - Tiefgarage/P+R (kein Auto-Zugang zum ÖV im Modell), Velo-KAPAZITÄT,
    #     Aufenthaltsqualität, Sicherheit, Wohn-/Gewerbeentwicklung, Lärm
    "stations": {
        "name": "Paket A – Bahnhofraum, Umsteigekante, Wege & 400 Veloplätze",
 
        "mobility_hubs": [
            {
                "name": "Hub Forch – Umsteigekante, direkte Wege, Velostation",
                "zones": [ZONE_FORCH],
                "stops_per_zone": 2,  # Bushalt Forch Bahnhof (8590613) + S18-Station Forch
                "effects": {
                    "access_time_reduction_pct": A2_ACCESS_EGRESS_PCT,    # A2: Umwegfaktor 1.40 -> 1.15
                    "egress_time_reduction_pct": A2_ACCESS_EGRESS_PCT,    # A2: gleiche Wege, Gegenrichtung
                    "transfer_time_reduction_pct": A1_TRANSFER_TIME_PCT,  # A1: Umsteigeweg 2.0 -> 0.5 min
                },
            }
        ],
 
        # A3: Tempo 30 (Abschnitte aus Editor 3.2)
        "road_capacity": FORCHSTRASSE_TEMPO30,
 
        # Kosten (Ansätze Vorjahresbericht Kap. 3.2, sonst als ANNAHME markiert):
        #   Tiefgarage 150 x 60'000                 = 9'000'000
        #   Platz 3'800 m2 x 750                     = 2'850'000
        #   Velostation 400 x 1'800                  =   720'000
        #   A1 Bushalt am Perron (Ansatz Haltestelle)=   600'000
        #   A2 Fuss-/Velowege 1'000 m x 1'200/m      = 1'200'000   ANNAHME (Belagsweg 3 m)
        #   A3 Tempo 30, Querung, Markierung         =   150'000   ANNAHME
        #   Total                                    = 14'520'000
        # Betrieb (im Bericht ausweisen):
        #   150 x 800 + 3'800 x 11.50 + 400 x 35 + 800 (Haltestelle) ≈ 178'500 CHF/Jahr
        # CO2-Emissionen Bau:
        #   Tiefgarage 150 x 1 = 150; Platz 3'800 x 0.16 = 608; Velo 400 x 0.02 = 8;
        #   Haltestelle 20 x 0.14 = 2.8; Wege 3'000 m2 x 0.16 = 480 (ANNAHME: Ansatz Platz)
        #   Total ≈ 1'249 t
        "appraisal": {
            "capital_cost_chf": 14_520_000,
            "lifetime_years": 60,    # Lebensdauer Tiefgarage/Bauwerk
            "capital_share": 0.94,   # langlebig: (9.0 + 2.85 + 0.6 + 1.2) / 14.52 Mio.
            "construction_co2_tonnes": 1_249,
        },
    },
 
    # -------------------------------------------------------------------------
    # PAKET B – Busangebot Forch – Glattal: 15'-Takt, Anschlusssicherung, Busbevorzugung ("tunnel")
    # -------------------------------------------------------------------------
    # Ausgangslage (Stage 0): Bus 706, 2 Busse, 30'-Takt (in den Skims enthalten).
    # Physisch:
    #   - 2. Buslinie mit 2 neuen E-Bussen, versetzt zu Bus 706 -> 4 Busse, 15'-Takt
    #   - Warteplatz für den zweiten Bus in Forch (Endhaltestelle)
    #   - B1: Fahrplan auf S18 abgestimmt, Anschlusssicherung in Forch
    #   - B3: Lichtsignal-Priorisierung Forch – Aesch – Ebmatingen
    # Im Modell (railway_expansions = ÖV-Skims, gilt auch für Bus):
    #   - Forch, Aesch -> Glattal (Einstieg Bus): Startwartezeit -50 %, Fahrzeit -7 bis -11 %
    #   - Scheuren, Zumikon, Egg -> Glattal (Umstieg in Forch): Umsteigewartezeit -70 %,
    #     Fahrzeit -6 bis -9 %
    #   (Zumikon -> Schwerzenbach nicht: Route im Modell via Zürich)
    # Nicht im Modell: Komfort, Zuverlässigkeit, Busbetriebskosten (siehe unten!).
    "tunnel": {
        "name": "Paket B – Bus Forch–Glattal: 15'-Takt, Anschluss & Bevorzugung",
 
        "railway_expansions": _bus_entries(),
 
        # Kosten (Ansätze Vorjahresbericht Kap. 3.2, sonst als ANNAHME markiert):
        #   2 E-Busse x 1'000'000                    = 2'000'000
        #   Warteplatz 2. Bus (halber Haltestellen-Ansatz) = 300'000   ANNAHME
        #   B3 LSA-Priorisierung 3 Knoten x 80'000   =   240'000   ANNAHME
        #   B1 Fahrplanabstimmung                     =         0   (betrieblich)
        #   Total                                    = 2'540'000
        # Betrieb (im Bericht ausweisen!): 2 x 400'000 + 400 + LSA-Unterhalt ≈ 805'000 CHF/Jahr.
        #   ACHTUNG: Das Modell setzt OPEX pauschal als Anteil CAPEX an (Stage-Übersicht
        #   zeigte 2 %) -> Busbetrieb massiv unterschätzt. In der Bewertung korrigieren.
        # CO2-Emissionen Bau: Warteplatz 10 x 0.14 = 1.4; LSA vernachlässigbar.
        "appraisal": {
            "capital_cost_chf": 2_540_000,
            "lifetime_years": 30,    # Lebensdauer Warteplatz/LSA
            "capital_share": 0.21,   # langlebig: (0.3 + 0.24) / 2.54 Mio. (Busse ~12 J. -> kein Restwert)
            "construction_co2_tonnes": 1.4,
        },
    },
}
 
# =============================================================================
# 2. COMBINED-ONLY BENEFITS
# =============================================================================
# Combined = Paket A + Paket B, NICHTS Zusätzliches.
# (A1 kürzt den Umsteigeweg, B1 die Umsteigewartezeit – verschiedene Komponenten,
#  darum keine Doppelzählung.)
COMBINED_EFFECTS = {
    "railway_expansions": [],
}
 
 
# =============================================================================
# INTERNAL ASSEMBLY AND APPRAISAL HELPERS (normally leave unchanged)
# =============================================================================
STATE_IDS = (0, 1, 2, 3)
STATE_LABELS = {0: "Baseline", 1: "Paket A only", 2: "Paket B only", 3: "Paket A + B"}
STATE_COLORS = {0: "#9E9E9E", 1: "#FFC107", 2: "#2196F3", 3: "#4CAF50"}
_STATE_COMPONENTS = {0: (False, False), 1: (True, False), 2: (False, True), 3: (True, True)}
 
 
def _railway_entries(package: dict) -> list[dict]:
    """Use the same list (or single dictionary) form as native interventions."""
    entries = package.get("railway_expansions") or []
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("railway_expansions must be a list of intervention dictionaries.")
    return entries
 
 
def _package_railway_effect(package: dict, key: str) -> float:
    """Sum an additive section/service assumption across railway entries."""
    total = 0.0
    entries = _railway_entries(package)
    if key == "section_time_saving_min":
        entries = [package, *entries]
    for entry in entries:
        try:
            value = float(entry.get(key, 0.0))
        except (TypeError, ValueError) as error:
            raise ValueError(f"{key} must be a finite nonnegative number.") from error
        if not isfinite(value) or value < 0:
            raise ValueError(f"{key} must be a finite nonnegative number.")
        total += value
    return total
 
 
def _railway_od_interventions(package: dict) -> list[dict]:
    """Keep OD interventions after extracting section/service assumptions."""
    settings = {"section_time_saving_min", "headway_reduction_min", "capacity_increase"}
    interventions = []
    for entry in _railway_entries(package):
        intervention = {key: deepcopy(value) for key, value in entry.items() if key not in settings}
        if intervention.keys() - {"name", "description"}:
            interventions.append(intervention)
    return interventions
 
 
def package_parameter_defaults() -> dict:
    """Expose package inputs under the shared appraisal/uncertainty parameter keys."""
    values = {}
    for number, name in enumerate(("stations", "tunnel"), 1):
        package = PACKAGES[name]
        values[f"C_INV_STAGE{number}"] = package["appraisal"]["capital_cost_chf"]
        values[f"CAPACITY_INCREASE_STAGE{number}"] = _package_railway_effect(package, "capacity_increase")
    values["CAPACITY_INCREASE_COMBINED"] = _package_railway_effect(COMBINED_EFFECTS, "capacity_increase")
    return values
 
 
def package_appraisal_settings() -> dict:
    """Appraisal cache inputs, read from the single package configuration."""
    return {
        "asset_lifetimes": {
            name: {key: package["appraisal"][key] for key in ("lifetime_years", "capital_share")}
            for name, package in PACKAGES.items()
        },
        "construction_emissions": {
            name: package["appraisal"]["construction_co2_tonnes"]
            for name, package in PACKAGES.items()
            if "construction_co2_tonnes" in package["appraisal"]
        },
    }
 
 
def get_stages(params: dict | None = None, *, packages: dict | None = None,
               combined_effects: dict | None = None) -> dict[int, dict]:
    """Assemble baseline (0), stations (1), tunnel (2), and both packages (3).
 
    Each package's physical effects are included once, with combined-only
    effects added to state 3. Appraisal settings stay outside the transport
    specifications. A third independently scheduled package needs model changes.
    Optional package arguments support notebook exploration without changing
    the saved PACKAGES or COMBINED_EFFECTS definitions.
    """
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}
 
    # Waiting effects cover different corridor municipalities in both directions.
    # Section in-vehicle savings instead follow parameters.SECTION route coverage.
    service_od_pairs = [
        {"origin": {"municipality_name": o}, "destination": {"municipality_name": d}}
        for o, d in itertools.combinations(p.CORRIDOR_MUNICIPALITIES, 2)
    ]
    return _assemble_stages(
        PACKAGES if packages is None else packages, params, service_od_pairs,
        combined_effects=combined_effects,
    )
 
 
def stage_components(stage: int) -> tuple[bool, bool]:
    """Return whether the station and tunnel packages are operating."""
    return _STATE_COMPONENTS[int(stage)]
 
 
def state_for_components(stations_active: bool, tunnel_active: bool) -> int:
    """Select a transport state from two independently operating packages."""
    components = (bool(stations_active), bool(tunnel_active))
    return next(state for state, active in _STATE_COMPONENTS.items() if active == components)
 
 
def stage_headway(stage: int, params: dict | None = None) -> float:
    """Minutes between services after additive package and combined-only savings."""
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}
    headway = float(params["PT_HEADWAY_BASELINE"])
    if not isfinite(headway) or headway <= 0:
        raise ValueError("PT_HEADWAY_BASELINE must be finite and positive.")
    reduction = _stage_minute_effect(stage, "headway_reduction_min")
    if reduction >= headway:
        raise ValueError("Total headway reduction must be smaller than PT_HEADWAY_BASELINE.")
    return headway - reduction
 
 
def _stage_minute_effect(stage: int, key: str) -> float:
    """Sum configured package minutes, adding the bonus only when both operate."""
    active_packages = stage_components(stage)
    packages = [PACKAGES[name]
                for name, active in zip(("stations", "tunnel"), active_packages) if active]
    if all(active_packages):
        packages.append(COMBINED_EFFECTS)
    return sum(_package_railway_effect(package, key) for package in packages)
 
 
def stage_capacity(stage: int, params: dict | None = None) -> float:
    """Peak-hour comfort threshold with package increases and a combined-only bonus."""
    import parameters as p
    params = {**p.NOMINAL_PARAMS, **(params or {})}
    baseline = float(params["PT_CAPACITY_BASELINE"])
    if not isfinite(baseline) or baseline <= 0:
        raise ValueError("PT_CAPACITY_BASELINE must be finite and positive.")
    increase = 0.0
    for package, active in enumerate(stage_components(stage), 1):
        value = float(params[f"CAPACITY_INCREASE_STAGE{package}"])
        if not isfinite(value) or value < 0:
            raise ValueError("Capacity increases must be finite nonnegative fractions.")
        if active:
            increase += value
    bonus = float(params["CAPACITY_INCREASE_COMBINED"])
    if not isfinite(bonus) or bonus < 0:
        raise ValueError("Combined capacity increase must be a finite nonnegative fraction.")
    if all(stage_components(stage)):
        increase += bonus
    return baseline * (1.0 + increase)
 
 
def _service_wait_effects(stage: int, params: dict) -> dict:
    """Convert the final state headway to one initial/transfer waiting reduction."""
    reduction = 100.0 * (1.0 - stage_headway(stage, params) / stage_headway(0, params))
    return {"initial_wait_reduction_pct": reduction, "transfer_wait_reduction_pct": reduction}
 
 
def _assemble_stages(packages: dict, params: dict, service_od_pairs: list[dict], *,
                     combined_effects: dict | None = None) -> dict[int, dict]:
    """Expand concise inputs to the existing native schema and combine packages."""
    combined_effects = COMBINED_EFFECTS if combined_effects is None else combined_effects
 
    def minute_effect(stage: int, key: str) -> float:
        active = stage_components(stage)
        selected = [packages[name] for name, enabled in zip(("stations", "tunnel"), active) if enabled]
        if all(active):
            selected.append(combined_effects)
        return sum(_package_railway_effect(package, key) for package in selected)
 
    technology = {
        "ebike_share": float(params["EBIKE_SHARE"]),
        "EBIKE_SPEED_MULTIPLIER": float(params["EBIKE_SPEED_MULTIPLIER"]),
    }
    # Native intervention defaults, not additional student assumptions.
    effect_defaults = {
        "railway_expansions": dict.fromkeys((
            "travel_time_reduction_pct", "speed_increase_pct", "distance_reduction_pct",
            "initial_wait_reduction_pct", "transfer_wait_reduction_pct",
            "transfer_time_reduction_pct", "access_time_reduction_pct", "egress_time_reduction_pct",
        ), 0.0),
        "mobility_hubs": dict.fromkeys((
            "access_time_reduction_pct", "transfer_time_reduction_pct",
            "initial_wait_reduction_pct", "transfer_wait_reduction_pct", "egress_time_reduction_pct",
        ), 0.0),
    }
    stages = {0: {"name": "Stage 0 – Baseline Network", "section_time_saving_min": 0.0, **technology}}
    for stage, package in ((1, "stations"), (2, "tunnel")):
        inputs = deepcopy(packages[package])
        inputs.pop("appraisal", None)
        inputs.pop("section_time_saving_min", None)
        inputs.pop("railway_expansions", None)
        for key in ("mobility_hubs", "bike_highways", "road_capacity"):
            if isinstance(inputs.get(key), dict):
                inputs[key] = [inputs[key]]
        railway_od = _railway_od_interventions(packages[package])
        if railway_od:
            inputs["railway_expansions"] = railway_od
        specification = {
            "name": inputs.pop("name"),
            "section_time_saving_min": minute_effect(stage, "section_time_saving_min"),
            **technology, **inputs,
        }
        stages[stage] = specification
    combined = deepcopy(stages[2])
    combined["name"] = "Paket A + B – Mobility Hub Forch"
    combined["section_time_saving_min"] = minute_effect(3, "section_time_saving_min")
    for key in ("railway_expansions", "mobility_hubs", "bike_highways", "road_capacity"):
        if key in stages[1] or key in stages[2] or key in combined_effects:
            bonus = (_railway_od_interventions(combined_effects) if key == "railway_expansions"
                     else combined_effects.get(key, []))
            if isinstance(bonus, dict):
                bonus = [bonus]
            combined[key] = deepcopy(stages[1].get(key, []) + stages[2].get(key, []) + bonus)
    stages[3] = combined
    for stage, specification in stages.items():
        if stage:
            headway = float(params["PT_HEADWAY_BASELINE"])
            reduction = minute_effect(stage, "headway_reduction_min")
            if not isfinite(headway) or headway <= 0 or reduction >= headway:
                raise ValueError("Total headway reduction must be smaller than a positive PT_HEADWAY_BASELINE.")
            wait_effect = 100.0 * (1.0 - (headway - reduction) / headway)
            # One final service-frequency intervention avoids compounding the
            # packages' percentages when their minute savings are additive.
            specification.setdefault("railway_expansions", []).append({
                "name": "Corridor service frequency",
                "area_pairs": deepcopy(service_od_pairs),
                "both_directions": True,
                "effects": {"initial_wait_reduction_pct": wait_effect,
                            "transfer_wait_reduction_pct": wait_effect},
            })
        for key, defaults in effect_defaults.items():
            for intervention in specification.get(key, []):
                intervention["effects"] = {**defaults, **intervention.get("effects", {})}
    return stages
 
 
def construction_emissions_tonnes(package: int | str) -> float:
    """Total construction tonnes CO2e for package 1/stations or 2/tunnel."""
    package_names = {1: "stations", 2: "tunnel", "stations": "stations", "tunnel": "tunnel"}
    if isinstance(package, bool) or package not in package_names:
        raise ValueError("Construction emissions package must be 1/'stations' or 2/'tunnel'.")
    try:
        value = float(PACKAGES[package_names[package]]["appraisal"].get("construction_co2_tonnes", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError("Construction emissions must be finite nonnegative tonnes CO2e.") from error
    if not isfinite(value) or value < 0:
        raise ValueError("Construction emissions must be finite nonnegative tonnes CO2e.")
    return value
 
 
def asset_residual_value(package: int | str, investment_chf: float, operated_years: float) -> float:
    """Undiscounted CHF remaining at horizon end for one built package.
 
    Package IDs 1 and 2 mean stations and tunnel, respectively. Transport state 3
    combines both packages, so value each package separately. Named packages
    "stations" and "tunnel" are accepted too. The caller supplies actual capital
    paid, omits unbuilt packages, and discounts the credit in the final year.
    """
    package_names = {1: "stations", 2: "tunnel", "stations": "stations", "tunnel": "tunnel"}
    if isinstance(package, bool) or package not in package_names:
        raise ValueError("Residual valuation package must be 1/'stations' or 2/'tunnel'.")
    settings = PACKAGES[package_names[package]]["appraisal"]
    try:
        investment = float(investment_chf)
        age = float(operated_years)
        share = float(settings["capital_share"])
    except (TypeError, ValueError) as exc:
        raise ValueError("Asset investment_chf, operated_years and capital_share must be numeric.") from exc
    if not isfinite(investment) or investment < 0:
        raise ValueError("Asset investment_chf must be finite and nonnegative.")
    if not isfinite(age) or age < 0:
        raise ValueError("Asset operated_years must be finite and nonnegative.")
    if not isfinite(share) or not 0 <= share <= 1:
        raise ValueError("Asset capital_share must be a finite fraction between zero and one.")
    if share == 0:
        return 0.0
    try:
        lifetime = float(settings["lifetime_years"])
    except (TypeError, ValueError) as exc:
        raise ValueError("An enabled asset lifetime_years must be finite and positive.") from exc
    if not isfinite(lifetime) or lifetime <= 0:
        raise ValueError("An enabled asset lifetime_years must be finite and positive.")
    return investment * share * max(0.0, 1.0 - age / lifetime)

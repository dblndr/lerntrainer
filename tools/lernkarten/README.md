# Lernkarten erzeugen

Druckbare A4-Karteikarten aus `vokabeln.json`: vorne Englisch, hinten Deutsch,
3×8 Karten je Blatt, Duplex an der **langen Kante**, Schnittlinien, Seitenangabe
unten rechts. Das Layout entspricht den bisherigen Karten
(`lernkarten-duplex.pdf`, Stand 24.10.2026, v001–v212).

Es stehen keine echten Namen auf den Karten. Der Spielstand-Schlüssel
`anton-vokabeln-v1` und die App-Dateien werden von diesem Generator nicht verändert.

## Drucken

1. Beidseitig, an der langen Kante spiegeln (Duplex long edge).
2. Maßstab 100 % / tatsächliche Größe, nicht an die Seite anpassen.
3. Entlang der Schnittlinien ausschneiden.

Zum Testen der Druckereinstellung bleibt `lernkarten-testseite.pdf` im
Repository-Stamm (nur 24 nummerierte Felder).

## Aktueller Stand

Der jeweils zuletzt erzeugte Stand steht in [`lernkarten/STAND.json`](../../lernkarten/STAND.json).

- Gesamtset: alle Vokabeln aus `vokabeln.json`.
- Delta-Set: nur Vokabeln mit einer ID *nach* dem letzten Kartenstand
  (aktuell nach `v212`, also v213–v306).

Die älteren Dateien `lernkarten-duplex.pdf` und `lernkarten-testseite.pdf` im
Repository-Stamm bleiben als bisheriger Druckstand (v001–v212) liegen.

## Regel bei Datenbank-Updates

**Immer wenn `vokabeln.json` erweitert oder geändert wird, die Lernkarten
mit diesem Generator neu erzeugen und das Delta ab der zuletzt gedruckten ID
mitliefern.** Die neue letzte ID und die Dateipfade in `STAND.json` eintragen.

## Aufruf

Voraussetzungen: Python 3, [ReportLab](https://pypi.org/project/reportlab/) und
die Schrift DejaVu Sans (`fonts-dejavu-core` unter Debian/Ubuntu, oder die
TTF-Dateien nach `tools/lernkarten/fonts/` legen).

```bash
python3 -m venv .venv
.venv/bin/pip install reportlab

# Gesamtset und Delta ab einer ID, plus STAND.json
.venv/bin/python tools/lernkarten/generate.py --gesamt --delta-nach v212 --stand

# Nur Gesamtset
.venv/bin/python tools/lernkarten/generate.py --gesamt

# Nur Delta: alles nach der angegebenen ID
.venv/bin/python tools/lernkarten/generate.py --delta-nach v306 --stand
```

Die PDFs landen in `lernkarten/lernkarten-gesamt-JJJJ-MM-TT.pdf` und
`lernkarten/lernkarten-delta-JJJJ-MM-TT.pdf`. Datum, JSON-Pfad und Zielordner
lassen sich mit `--datum`, `--json` und `--out-dir` überschreiben.

Diese Dateien gehören nicht in `index.html`. Ein Merge nach `main` würde sie
über GitHub Pages mitveröffentlichen; dafür ist eine eigene Freigabe nötig.

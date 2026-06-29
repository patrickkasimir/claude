#!/usr/bin/env python3
"""Minimaler PDF-Generator ohne externe Libraries.

Erzeugt eine einseitige A4-PDF mit fetter Ueberschrift + Fliesstext
(Helvetica, WinAnsi/cp1252 -> deutsche Umlaute funktionieren).
Reicht fuer generische Vertragsvorlagen.
"""
from __future__ import annotations

import textwrap
from pathlib import Path


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(path: str | Path, title: str, paragraphs: list[str]) -> Path:
    # Zeilen umbrechen
    lines: list[str] = []
    for p in paragraphs:
        if not p:
            lines.append("")
        else:
            lines.extend(textwrap.wrap(p, width=95) or [""])

    parts = [f"BT /F1 18 Tf 50 800 Td ({_esc(title)}) Tj ET",
             "BT /F2 10 Tf 50 770 Td 14 TL"]
    for ln in lines:
        parts.append(f"({_esc(ln)}) Tj T*")
    parts.append("ET")
    content = "\n".join(parts).encode("cp1252", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >>",
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
    ]

    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += ("%d 0 obj\n" % i).encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    n = len(objects) + 1
    out += ("xref\n0 %d\n" % n).encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += ("trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF"
            % (n, xref_pos)).encode()

    path = Path(path)
    path.write_bytes(out)
    return path


# --- Generische Vorlagen-Texte je Vertragsart -------------------------------
_FOOTER = [
    "",
    "____________________________________________________________________",
    "Mustervorlage – unverbindlich, ersetzt keine Rechtsberatung.",
    "Erstellt automatisch zu Demonstrationszwecken (Lieferantenvertragsmanagement).",
]

TEMPLATES = {
    "avv": ("Auftragsverarbeitungsvertrag (AVV)", [
        "zwischen [Verantwortlicher] (nachfolgend 'Verantwortlicher')",
        "und [Lieferant] (nachfolgend 'Auftragsverarbeiter').",
        "",
        "1. Gegenstand und Dauer der Verarbeitung",
        "Der Auftragsverarbeiter verarbeitet personenbezogene Daten ausschliesslich "
        "im Auftrag und nach Weisung des Verantwortlichen gemaess Art. 28 DSGVO.",
        "",
        "2. Art und Zweck der Verarbeitung",
        "Umfang, Art und Zweck der Verarbeitung ergeben sich aus dem zugrunde "
        "liegenden Hauptvertrag sowie der Anlage 'Verarbeitungstaetigkeiten'.",
        "",
        "3. Technisch-organisatorische Massnahmen (TOM)",
        "Der Auftragsverarbeiter gewaehrleistet geeignete TOM nach Art. 32 DSGVO "
        "(Vertraulichkeit, Integritaet, Verfuegbarkeit, Belastbarkeit).",
        "",
        "4. Unterauftragsverhaeltnisse",
        "Die Einbindung weiterer Unterauftragsverarbeiter bedarf der vorherigen "
        "Zustimmung des Verantwortlichen.",
        "",
        "5. Betroffenenrechte und Unterstuetzungspflichten",
        "Der Auftragsverarbeiter unterstuetzt den Verantwortlichen bei der "
        "Erfuellung der Betroffenenrechte sowie bei Meldepflichten.",
    ] + _FOOTER),
    "nda": ("Geheimhaltungsvereinbarung (NDA)", [
        "zwischen [Auftraggeber] und [Lieferant].",
        "",
        "1. Vertrauliche Informationen",
        "Als vertraulich gelten alle muendlich, schriftlich oder elektronisch "
        "ueberlassenen Informationen, die als vertraulich gekennzeichnet sind "
        "oder ihrer Natur nach als vertraulich anzusehen sind.",
        "",
        "2. Geheimhaltungspflicht",
        "Die Parteien verpflichten sich, vertrauliche Informationen streng "
        "geheim zu halten und ausschliesslich fuer den vereinbarten Zweck zu nutzen.",
        "",
        "3. Ausnahmen",
        "Die Pflicht entfaellt fuer Informationen, die nachweislich oeffentlich "
        "bekannt sind oder rechtmaessig von Dritten erlangt wurden.",
        "",
        "4. Dauer",
        "Die Geheimhaltungspflicht gilt fuer die Dauer der Zusammenarbeit sowie "
        "fuer einen Zeitraum von [X] Jahren nach deren Beendigung.",
        "",
        "5. Rueckgabe und Loeschung",
        "Nach Beendigung sind vertrauliche Unterlagen zurueckzugeben oder "
        "nachweislich zu loeschen.",
    ] + _FOOTER),
    "rahmenvertrag": ("Rahmenvertrag", [
        "zwischen [Auftraggeber] und [Lieferant].",
        "",
        "1. Zweck des Rahmenvertrags",
        "Dieser Rahmenvertrag regelt die allgemeinen Bedingungen fuer kuenftige "
        "Einzelbestellungen und Einzelvereinbarungen zwischen den Parteien.",
        "",
        "2. Geltungsbereich",
        "Die Bedingungen gelten fuer alle auf Basis dieses Rahmenvertrags "
        "geschlossenen Einzelvereinbarungen und Bestellungen.",
        "",
        "3. Preise und Konditionen",
        "Es gelten die im Anhang vereinbarten Preise und Konditionen, sofern "
        "in Einzelvereinbarungen nichts Abweichendes geregelt ist.",
        "",
        "4. Laufzeit und Verlaengerung",
        "Der Rahmenvertrag laeuft ab [Startdatum] und verlaengert sich "
        "automatisch, sofern er nicht fristgerecht gekuendigt wird.",
        "",
        "5. Kuendigung",
        "Die Kuendigung ist unter Einhaltung der vereinbarten Frist zum "
        "Vertragsende moeglich.",
    ] + _FOOTER),
    "einzelvereinbarung": ("Einzelvereinbarung", [
        "zum Rahmenvertrag [Rahmenvertragsnummer]",
        "zwischen [Auftraggeber] und [Lieferant].",
        "",
        "1. Bezug zum Rahmenvertrag",
        "Diese Einzelvereinbarung konkretisiert den uebergeordneten Rahmenvertrag "
        "und ergaenzt dessen Bedingungen fuer den konkreten Leistungsgegenstand.",
        "",
        "2. Leistungsgegenstand",
        "Gegenstand ist die Lieferung/Leistung gemaess der beigefuegten "
        "Leistungsbeschreibung.",
        "",
        "3. Liefer- und Leistungszeitraum",
        "Der vereinbarte Zeitraum ergibt sich aus den Feldern Start- und Enddatum "
        "dieses Vertrags.",
        "",
        "4. Verguetung",
        "Die Verguetung richtet sich nach den im Rahmenvertrag hinterlegten "
        "Konditionen, soweit hier nicht abweichend geregelt.",
        "",
        "5. Sonstiges",
        "Im Uebrigen gelten die Regelungen des Rahmenvertrags entsprechend.",
    ] + _FOOTER),
}


def generate_all(out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {}
    for key, (title, paras) in TEMPLATES.items():
        result[key] = make_pdf(out_dir / f"{key}.pdf", title, paras)
    return result


if __name__ == "__main__":
    paths = generate_all(Path(__file__).parent / "templates")
    for k, p in paths.items():
        print(f"{k:<18} -> {p} ({p.stat().st_size} Bytes)")

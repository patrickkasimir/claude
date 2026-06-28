# Dedizierten API-Benutzer für die Analyse anlegen (Odoo)

**Warum:** Nicht das persönliche Admin-Konto für die Analyse verwenden, sondern
einen **eigenen, dedizierten Benutzer** mit einem **eigenen API-Key**. Vorteile:

- Der Key lässt sich **jederzeit einzeln widerrufen**, ohne andere Logins zu stören.
- Der Zugriff ist **klar einer Identität zugeordnet** (Nachvollziehbarkeit/Logs).
- Der Benutzer kann nach der Analyse **deaktiviert** werden.

> Hinweis zur Berechtigung: Die Analyse liest viele **Konfigurations-/Technik-Modelle**
> (Benutzergruppen, Datensatzregeln, Zugriffsrechte, Module, Automatisierungen …).
> Diese sind in Odoo meist nur mit **„Einstellungen/Administration"**-Rechten lesbar.
> Ein streng lese-beschränkter Benutzer funktioniert zwar für die Grunddaten, liefert
> aber **unvollständige** Sicherheits-/Technik-Analysen. Empfehlung daher: dedizierter
> Benutzer **mit** Administrationsrechten, aber getrennt vom Tagesgeschäft und mit
> widerrufbarem Key.

## Schritt für Schritt

1. **Benutzer anlegen**
   Einstellungen → *Benutzer & Unternehmen* → *Benutzer* → **Neu**.
   - Name: z. B. `Analyzer (Service)`
   - E-Mail/Login: z. B. `analyzer@deinefirma.de`
   - Benutzertyp: **Intern**

2. **Rechte vergeben**
   - Für die **vollständige** Analyse: Gruppe **Administration → Einstellungen** setzen.
   - Für eine **minimale** Variante: nur die *Benutzer*-Gruppen der relevanten Apps
     (kein Settings) → dann fehlen die Abschnitte Sicherheit/Technik teilweise.

3. **API-Key erzeugen**
   Als dieser Benutzer (oder über *Benutzer → Konto-Sicherheit*):
   *Mein Profil* → Reiter **Konto-Sicherheit** → **Neuer API-Schlüssel** →
   Zweck „Analyzer", Schlüssel kopieren.
   (Voraussetzung: in Odoo ist *Entwicklermodus*/API-Keys aktiviert.)

4. **Im Analyzer hinterlegen**
   Instanz mit URL, Datenbank und diesem **Login** erfassen. Den **API-Key** erst
   beim **Analysieren** eingeben – er wird **nicht gespeichert**.

## Widerrufen

Key nicht mehr gebraucht oder kompromittiert?
*Konto-Sicherheit* des Benutzers → API-Schlüssel **löschen**, oder den
**Benutzer deaktivieren**. Sofort wirksam, betrifft nur diesen Zugang.

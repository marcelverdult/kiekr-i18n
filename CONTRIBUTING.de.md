# Mitwirken an Übersetzungen

Danke fürs Mithelfen bei der Übersetzung von KiekR. Dieses Dokument
erklärt das Dateiformat, was nicht angefasst werden soll, und wie du
deine Änderungen lokal testen kannst.

## Kurzüberblick

```
locales/
  en.json   ← Quelltext — NICHT ÄNDERN (Verwaltung durch KiekR-Team)
  de.json   ← Verwaltung durch KiekR-Team — NICHT ÄNDERN
  es.json   ← bearbeiten für Spanisch
  fr.json   ← bearbeiten für Französisch
  nl.json   ← bearbeiten für Niederländisch
  <code>.json ← neu anlegen für eine neue Sprache
```

## Dateiformat

Jede Sprachdatei ist ein flaches JSON-Objekt. Jeder Schlüssel ist eine
stabile Kennung; **nicht umbenennen**.

Ein Wert kann eine von drei Formen haben:

### 1. Einfacher String

```json
"login_title": "Anmelden"
```

Die Übersetzung wurde menschlich geprüft und ist auslieferungsfertig.

### 2. Objekt mit Metadaten

```json
"login_title": {
  "value": "Anmelden",
  "_human": true
}
```

Wie ein einfacher String, zusätzlich mit Vermerk, wer den Wert erzeugt
hat:

| Feld     | Bedeutung                                              |
|----------|--------------------------------------------------------|
| `_human` | Wert wurde menschlich geprüft und freigegeben          |
| `_ai`    | Per DeepL o. ä. maschinell vorausgefüllt               |
| `_seeded`| ISO-Datum, an dem die KI-Befüllung geschrieben wurde   |

Wenn du einen KI-vorgefüllten Wert bearbeitest, ändere `_ai` zu
`_human` (oder ersetze das ganze Objekt durch einen einfachen String).

### 3. `null`

```json
"login_title": null
```

Noch nicht übersetzt. Die App fällt auf Englisch zurück.
**Nicht löschen** — den Schlüssel mit `null` lassen, wenn du nicht
übersetzen kannst.

## Platzhalter

Manche Strings enthalten Platzhalter. Sie sind im positionellen
Android-Stil geschrieben:

```
"chat_clear_confirm_body": "%1$d Nachrichten werden gelöscht. Das kann nicht rückgängig gemacht werden."
```

- `%1$d`, `%2$d`, … — Ganzzahlen
- `%1$s`, `%2$s`, … — Strings (Namen, Regionen usw.)

**Die gleichen Platzhalter müssen erhalten bleiben.** Du darfst sie in
deinem Satz umstellen — die Nummerierung sorgt für die richtige
Zuordnung.

## Plurale

Einige Schlüssel verwenden ICU-Pluralformat:

```json
"nodes_found": {
  "plural": {
    "one":   "# Knoten gefunden",
    "other": "# Knoten gefunden"
  }
}
```

`#` wird zur Laufzeit durch die Zahl ersetzt. `other` ist Pflicht.

## Was nicht änderbar ist

CI lehnt deinen PR ab, wenn du:

- einen Schlüssel umbenennst
- einen Schlüssel hinzufügst, der nicht in `en.json` steht
- `en.json` oder `de.json` änderst (außer du gehörst zum KiekR-Team)
- `_meta.*`-Felder änderst
- einen als nicht-übersetzbar markierten String übersetzt
  (z. B. den App-Namen)
- einen Platzhalter benutzt, der im englischen Original nicht
  vorkommt
- einen Plural ohne `other`-Kategorie abgibst

## Glossar

Technische Begriffe haben kanonische Übersetzungen, damit die App
konsistent bleibt. Siehe [glossary/](glossary/).

## Lokal testen

Die App-Quellen brauchst du nicht. JSON-Syntax wird per CI geprüft.
Lokal:

```sh
python3 tools/validate.py
```

## Pull-Request-Etikette

- Ein PR pro Sprache.
- Verwandte Schlüssel zusammen ändern.
- Bei vielen Änderungen kurz im PR-Body begründen.
- Geduld — Reviews erfolgen nach Verfügbarkeit.

## Verhaltenskodex

Sei freundlich. Übersetzen ist Urteilsfrage, und vernünftige
Übersetzer:innen sind unterschiedlicher Meinung. Vertraue
Muttersprachler:innen; streite über den Begriff, nicht über die Person.

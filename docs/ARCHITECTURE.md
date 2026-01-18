# KidsControl – Architektur

Version: v0.5  
Stand: Server-seitig stabil

## Zielbild

KidsControl ist eine **server-zentrierte Kindersicherungs-Lösung** für Linux-Clients.
Der Server trifft Entscheidungen, Clients setzen sie durch.

Der Server ist die **einzige Quelle der Wahrheit**.

## Grundannahmen

- Linux-Clients (Ubuntu, CachyOS, Bazzite)
- Zentrale Verwaltung
- Manipulationsresistenz durch Server-Autorität
- Keine Spyware, keine Inhaltsanalyse

## Rollen

### Server (ChildControl)

- hält alle Regeln und Zeitpläne
- entscheidet:
  - erlaubt
  - vorwarnen
  - blockieren
- protokolliert Entscheidungen nachvollziehbar
- kennt Kinder, nicht Benutzerkonten

### Client

- fragt Regeln ab
- setzt Entscheidungen lokal durch
- speichert minimalen Cache (zukünftig)
- trifft **keine eigenen Regeln**

## Active Directory / Domain

- AD-Integration ist **optional**
- Der Server selbst ist **nicht** AD-abhängig
- Clients können AD-Informationen nutzen (z. B. Benutzername → Kind)
- Kein hartes Vertrauen in Kerberos zur Laufzeit

## Kommunikationsprinzip

- Client → Server (pull)
- Server → Client (keine Push-Abhängigkeit)
- Offline-Szenarien werden später berücksichtigt

## Nicht-Ziele

- keine Inhaltsfilterung
- kein Keylogging
- keine Bildschirmüberwachung
- keine Umgehung elterlicher Verantwortung

## Fazit

KidsControl priorisiert **Erklärbarkeit, Stabilität und Kontrolle**  
über aggressive Durchsetzung oder technische Spielereien.

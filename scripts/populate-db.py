"""
populate-db.py — Engångsskript som fyller databasen med testdata.

VAD:
  Skapar 50 000 slumpmässiga transaktioner (10 000 per konto × 5 konton).
  Beloppen slumpas mellan -1000 och +1000 (insättningar och uttag).

HUR:
  1. Kopplar direkt till ../app-sanic/transactions.db via sqlite3
  2. Kör 50 000 INSERT-satser i en nästlad loop
  3. Committar alla på en gång (snabbt — ~1 sekund)

VARFÖR:
  Utan testdata har databasen bara den tomma tabellen som init_db() skapar.
  Man behöver massa rader för att kunna mäta prestanda, testa indexering,
  och se skillnaden mellan O(N) full scan vs O(log N) med INDEX.

BEROENDEN:
  ┌─────────────────────────────────────────────────────────────────┐
  │ populate-db.py                                                  │
  │      │                                                          │
  │      │  sqlite3.connect('../app-sanic/transactions.db')         │
  │      │  INSERT INTO transactions (account_id, amount)           │
  │      ▼                                                          │
  │ transactions.db  ◄── tabellen MÅSTE redan finnas                │
  │      ▲                                                          │
  │      │  CREATE TABLE IF NOT EXISTS transactions(...)            │
  │      │                                                          │
  │ server.py init_db()  ◄── måste köras FÖRST (starta servern)    │
  └─────────────────────────────────────────────────────────────────┘

  Ordning: starta servern → init_db() skapar tabellen → kör detta skript.
  Om du kör scriptet utan att servern startats → "no such table" error.

BEHÖVER JAG ÄNDRA DENNA FIL?
  Nej. Det här är ett lokalt testverktyg — det körs aldrig i CI.
  Att det använder sqlite3 (sync) istället för aiosqlite spelar ingen roll
  eftersom det är ett engångsskript, inte en server med parallella requests.
"""

# random: genererar slumpmässiga belopp för transaktionerna
import random
# sqlite3: synkront databasbibliotek — OK här (engångsskript, inte server)
import sqlite3

# Sökväg till databasen — relativ från scripts/ → upp en nivå → app-sanic/
# Scriptet MÅSTE köras från scripts/-mappen, annars hittas inte filen
DB_PATH = '../app-sanic/transactions.db'

# 5 testkonton — samma konton som Cypress-testerna kan referera till
ACCOUNT_IDS = ['account1', 'account2', 'account3', 'account4', 'account5']
# 10 000 transaktioner per konto × 5 konton = 50 000 rader totalt
# Tillräckligt för att se prestandaskillnad med/utan INDEX
TRANSACTIONS_PER_ACCOUNT = 10000


def populate_db():
    """Fyll databasen med slumpmässiga transaktioner.
    Alla INSERTs sker i samma transaktion (en commit i slutet) — snabbt."""
    # Öppna databasanslutning — with stänger automatiskt vid block-slut
    # OBS: sqlite3.connect() skapar filen om den inte finns, MEN tabellen
    # måste redan existera (skapas av init_db() i server.py)
    with sqlite3.connect(DB_PATH) as conn:
        # Skapa en cursor — ett objekt som kan köra SQL-satser
        cursor = conn.cursor()
        # Yttre loop: 10 000 varv (antal transaktioner per konto)
        for _ in range(TRANSACTIONS_PER_ACCOUNT):
            # Inre loop: 5 konton — varje varv skapar 1 transaktion per konto
            for account_id in ACCOUNT_IDS:
                # Slumpa belopp mellan -1000.00 och +1000.00
                # Negativt = uttag, positivt = insättning
                # round(..., 2) = avrunda till 2 decimaler (ören)
                amount = round(random.uniform(-1000, 1000), 2)
                # Parametriserad INSERT (?, ?) — skyddar mot SQL-injection
                # Varje INSERT skapar en rad med auto-genererat transaction_id
                cursor.execute(
                    'INSERT INTO transactions (account_id, amount) VALUES (?, ?)',
                    (account_id, amount)
                )
        # Spara ALLA 50 000 rader till disk i en enda commit
        # Utan explicit commit() gör sqlite3 auto-commit per INSERT — 100x långsammare
        conn.commit()

# __name__ == '__main__' → körs bara vid direkt exekvering: python populate-db.py
# Om filen importeras från en annan fil körs detta INTE
if __name__ == '__main__':
    # Kör populate-funktionen
    populate_db()
    # Skriv ut antal skapade transaktioner: 5 × 10 000 = 50 000
    print(f"Database populated with {len(ACCOUNT_IDS) * TRANSACTIONS_PER_ACCOUNT} transactions")
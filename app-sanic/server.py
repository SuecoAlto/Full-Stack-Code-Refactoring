"""
server.py — Backend-servern. All API-logik i en enda fil.

ENDPOINTS:
  GET  /ping                  → Hälsokontroll, returnerar {"result":"pong"}
  POST /transactions          → Skapar ny transaktion i databasen
  GET  /transactions          → Listar alla transaktioner (eller filtrerar med ?account_id=X)
  GET  /transactions/<id>     → Hämtar en specifik transaktion
  GET  /accounts/<id>         → Beräknar saldo via SUM(amount)
  GET  /accounts/count        → Antal unika konton + lista med ID:n

BEROENDEN:
  package.json (root):  "start:backend" → "cd app-sanic && sanic server.app"
  App.jsx:              fetch("http://localhost:8000/...") → denna fil
  Cypress:              cy.request("http://localhost:8000/...") → denna fil
  transactions.db:      SQLite-databasen, skapas automatiskt av init_db()

═══════════════════════════════════════════════════════════════════
OPTIMERINGSPLAN — 5 problem som måste åtgärdas
═══════════════════════════════════════════════════════════════════

PROBLEM 1: Synkron databas (sqlite3) blockerar event loopen
─────────────────────────────────────────────────────────────
  Sanic är en ASYNC webbserver — den hanterar tusentals requests via en
  enda tråd (event loop). Men sqlite3.connect() är SYNKRONT: medan en
  query körs FRYSER hela servern. Inga andra requests hanteras.

  Konsekvens: Om en GET /transactions tar 500ms (50 000 rader), kan ingen
  ens nå /ping under den tiden. Testresultat: /ping median 3776ms!

  Lösning: Byt till aiosqlite (redan i requirements.txt men oanvänt).
  aiosqlite kör SQLite-operationer i en bakgrundstråd och returnerar
  kontrollen till event loopen medan databasen arbetar.

  Före: with sqlite3.connect(DB_PATH) as conn:     ← BLOCKERAR
  Efter: async with aiosqlite.connect(DB_PATH) as conn:  ← ICKE-BLOCKERANDE

PROBLEM 2: Ingen INDEX på account_id
─────────────────────────────────────
  Varje WHERE account_id = ? kräver att SQLite läser VARJE rad i tabellen
  (full table scan, O(N)). Med 50 000 rader = 50 000 jämförelser.

  Med INDEX: SQLite bygger ett B-tree som gör lookup O(log N) ≈ 17 steg
  istället för 50 000. Filtreringar + SUM(amount) blir 100-1000x snabbare.

  Lösning: CREATE INDEX IF NOT EXISTS idx_account_id ON transactions(account_id)
  Trade-off: INDEX gör INSERT marginellt långsammare (~5%) men read-operationer
  blir dramatiskt snabbare. Värt det för read-heavy applikationer.

PROBLEM 3: Ingen WAL-mode (Write-Ahead Logging)
────────────────────────────────────────────────
  SQLites default journal_mode är "delete" — den låser HELA databasen vid
  write-operationer. Det betyder att reads blockeras under writes.

  Med WAL-mode kan flera readers läsa SAMTIDIGT som en writer skriver.
  Enda begränsningen: max 1 writer åt gången (men det är OK för denna app).

  Lösning: PRAGMA journal_mode=WAL i init_db()
  Effekt: Concurrent GET-requests blockeras inte av POST-requests.

PROBLEM 4: Ingen pagination
───────────────────────────
  GET /transactions returnerar ALLA rader på en gång. Med 50 000 rader:
  - SQLite måste läsa alla
  - Python måste konvertera alla till dicts
  - Sanic måste serialisera alla till JSON
  - Nätverket måste skicka allt

  Lösning: LIMIT/OFFSET eller cursor-baserad pagination.
  GET /transactions?page=1&limit=50 → returnera bara 50 åt gången.
  OBS: Cypress-testerna skapar och hämtar enskilda transaktioner,
  så pagination påverkar inte dem — men det förbättrar skalbarhet.

PROBLEM 5: Allt i en fil (kodstruktur)
───────────────────────────────────────
  All logik (app-setup, routes, DB-hantering) ligger i en enda fil.
  Det gör koden svår att testa, underhålla och förstå.

  Möjlig uppdelning:
    app-sanic/
      server.py       → app-setup + init + starta servern
      routes.py       → alla @app.route-handlers
      db.py           → databasanslutning, init_db(), helper-funktioner
      config.py       → DB_PATH, CORS_ORIGINS etc.

═══════════════════════════════════════════════════════════════════
"""

# Sanic: async Python-webbserver (som Express fast för Python)
from sanic import Sanic
# json: hjälpfunktion som returnerar HTTP-svar med Content-Type application/json
from sanic.response import json
# Extend: aktiverar CORS och andra tillägg via sanic-ext
from sanic_ext import Extend
# ⚠️ sqlite3: SYNKRONT databasbibliotek — BLOCKERANDE
# ───────────────────────────────────────────────────
# Python GIL + sync I/O = hela event loopen fryser under varje query.
# En enda långsam SELECT (t.ex. 50 000 rader) blockerar ALLA inkommande
# requests i 200-500ms. I testmiljön: /ping svarade på 3776ms istället
# för normala <5ms, dvs en 750x fördröjning.
#
# ERSÄTT MED:
#   import aiosqlite       ← finns redan i requirements.txt
#   async with aiosqlite.connect(DB_PATH) as conn:
#       cursor = await conn.execute(query)
#       rows = await cursor.fetchall()
#
# Skillnaden: aiosqlite delegerar I/O till en bakgrundstråd och
# returnerar kontrollen till event loopen via "await" — andra requests
# kan hanteras parallellt.
import sqlite3
# os: oanvänd import (kan tas bort vid refaktorering)
import os

# Skapa Sanic-appinstansen med ett namn (visas i loggar)
app = Sanic("Transaction-Management-App")
# Tillåt frontend på port 3000 att anropa backend på port 8000 (CORS)
# Utan detta blockerar webbläsaren fetch() från en annan origin
app.config.CORS_ORIGINS = "http://localhost:3000"
# Aktivera sanic-ext (registrerar CORS-middleware baserat på config ovan)
Extend(app)

# Sökväg till SQLite-databasen (relativ till app-sanic/)
DB_PATH = 'transactions.db'

def init_db():
    """Skapa databastabellen vid uppstart om den inte redan finns.
    Körs EN gång när server.py laddas (rad längre ner).

    ⚠️ OPTIMERINGSANALYS — denna funktion saknar två kritiska saker:

    1) INDEX på account_id:
       Utan INDEX gör SQLite full table scan för varje WHERE account_id = ?
       Det innebär O(N) = läs ALLA 50 000 rader för att hitta de ~50 som matchar.
       Med INDEX (B-tree): O(log N) lookup ≈ 17 trädnoder → direkt till rätt rader.
       Förbättring: ~100-1000x snabbare för filtrerade queries.
       Nackdel: marginellt (~5%) långsammare INSERTs (indexet måste uppdateras).

    2) WAL-mode (Write-Ahead Logging):
       Default journal_mode='delete': EXKLUSIVT lås vid write = alla reads blockeras.
       Med WAL: readers och writers kan jobba SIMULTANT.
       Resultat: POST /transactions blockerar inte GET /transactions.
       Aktiveras med: PRAGMA journal_mode=WAL (en gång, sparas i DB-filen).
    """
    # Öppna databasanslutning — with stänger automatiskt vid block-slut
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Skapa tabellen om den inte finns
        # transaction_id: auto-inkrementerande primärnyckel (B-tree index automatiskt)
        # account_id: textsträng (t.ex. "account1") — NOT NULL = obligatoriskt
        #   ⚠️ SAKNAR INDEX — gör alla WHERE account_id=? till O(N) full scan
        # amount: decimaltal (positivt = insättning, negativt = uttag)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                amount REAL NOT NULL
            )
        ''')
        # ⚠️ HÄR BÖR LÄGGAS TILL:
        # cursor.execute('CREATE INDEX IF NOT EXISTS idx_account_id ON transactions(account_id)')
        # cursor.execute('PRAGMA journal_mode=WAL')
        # Spara ändringarna till disk
        conn.commit()

# Kör init_db() direkt vid import/start — skapar tabellen om den saknas
init_db()


# === ENDPOINT: /ping ===
# Enkel hälsokontroll — Cypress testar att servern svarar
@app.route('/ping')
async def test(request):
    # Returnera JSON med statuskod 200 (default)
    return json({'result': 'pong'})


# === ENDPOINT: POST /transactions ===
# Skapa en ny transaktion i databasen
# ┌──────────────────────────────────────────────────────────────┐
# │ OPTIMERINGSANALYS:                                          │
# │ • INSERT på en enda rad = snabb operation (~1ms)            │
# │ • Men sync sqlite3 = event loop fryser ändå under den ms   │
# │ • Med WAL-mode: reads fortsätter oberoende av denna write   │
# │ • Med aiosqlite: event loopen frigörs under INSERT          │
# │ • Cypress skapar transaktioner här — ändra INTE response-   │
# │   formatet (transaction_id som sträng i JSON)               │
# └──────────────────────────────────────────────────────────────┘
@app.route('/transactions', methods=['POST'])
async def create_transaction(request):
    # Parsa JSON-body från request ({account_id: "...", amount: 123})
    data = request.json
    # Hämta fälten — .get() returnerar None om fältet saknas
    account_id = data.get('account_id')
    amount = data.get('amount')

    # Validera: båda fälten måste finnas
    if not account_id or amount is None:
        return json({'error': 'Invalid input'}, status=400)

    # ⚠️ SYNKRON DB-anslutning — blockerar event loopen under INSERT
    # Effekt: Alla andra requests (inkl. /ping) fryser tills INSERT är klar
    # Fix: async with aiosqlite.connect(DB_PATH) as conn:
    #        cursor = await conn.execute(...)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Parametriserad query (?, ?) — skyddar mot SQL-injection
        cursor.execute(
            'INSERT INTO transactions (account_id, amount) VALUES (?, ?)',
            (account_id, amount)
        )
        # Hämta det auto-genererade ID:t för den nya raden
        transaction_id = cursor.lastrowid
        # Spara till disk
        conn.commit()

    # Returnera det nya ID:t med statuskod 201 (Created)
    # Frontend använder detta för att sedan GET:a transaktionen
    return json({'transaction_id': str(transaction_id)}, status=201)


# === ENDPOINT: GET /transactions ===
# Hämta alla transaktioner, eller filtrera med ?account_id=X
# ┌──────────────────────────────────────────────────────────────┐
# │ OPTIMERINGSANALYS — MEST KRITISKA ENDPOINTEN:               │
# │                                                             │
# │ Problem 1: Sync sqlite3 blockerar event loopen              │
# │   50 000 rader → ~200-500ms total blockering                │
# │   Under den tiden: ALLA requests köas (inkl. /ping)         │
# │                                                             │
# │ Problem 2: Ingen INDEX på account_id                        │
# │   WHERE account_id = ? → full table scan O(N)               │
# │   Med INDEX: O(log N) lookup + O(K) för K matchande rader   │
# │   Uppmätt: 50 000 rader utan INDEX → ~150ms scan            │
# │            50 000 rader MED INDEX → ~0.5ms lookup           │
# │                                                             │
# │ Problem 3: Ingen pagination (LIMIT/OFFSET)                  │
# │   Utan filter hämtas ALLA rader → stort JSON-svar           │
# │   50 000 rader × ~100 bytes/rad ≈ 5MB JSON                 │
# │   Lösning: ?page=1&limit=50 → LIMIT 50 OFFSET 0            │
# │                                                             │
# │ Problem 4: fetchall() laddar allt i RAM                     │
# │   50 000 dict-objekt i Python-minnet på en gång             │
# │   Alternativ: streaming/cursor-baserad iteration            │
# └──────────────────────────────────────────────────────────────┘
@app.route('/transactions', methods=['GET'])
async def list_transactions(request):
    # Läs query parameter — t.ex. /transactions?account_id=account1
    account_id = request.args.get('account_id')
    # ⚠️ SYNKRON — blockerar event loopen, särskilt långsamt med 50 000+ rader
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if account_id:
            # Filtrerad query — ⚠️ utan INDEX: full table scan O(N) = läser ALLA rader
            # EXPLAIN QUERY PLAN visar "SCAN TABLE transactions" (dåligt)
            # Med INDEX hade det visat "SEARCH TABLE ... USING INDEX" (bra)
            cursor.execute(
                "SELECT transaction_id, account_id, amount FROM transactions WHERE account_id = ?",
                (account_id,)
            )
        else:
            # Hämta ALLA transaktioner — alltid O(N), oundvikligt utan pagination
            # ⚠️ Med 50 000 rader: ~5MB JSON-svar, ~200ms serialisering
            # Med LIMIT/OFFSET: O(LIMIT) data, snabbt svar
            cursor.execute("SELECT transaction_id, account_id, amount FROM transactions")
        # fetchall() laddar ALLA rader i minnet på en gång — O(N) minnesanvändning
        transactions = cursor.fetchall()
    # Konvertera tupler till dicts — frontend förväntar sig JSON med namngivna fält
    # transaction_id konverteras till sträng (frontend/Cypress förväntar sig det)
    result = [{"transaction_id": str(t[0]), "account_id": t[1], "amount": t[2]} for t in transactions]
    return json(result)


# === ENDPOINT: GET /transactions/<transaction_id> ===
# Hämta en specifik transaktion via dess ID
# ┌──────────────────────────────────────────────────────────────┐
# │ OPTIMERINGSANALYS:                                          │
# │ • Söker på PRIMARY KEY → redan O(log N) via inbyggt index  │
# │ • Enda problemet: sync sqlite3 blockerar event loopen       │
# │ • Fix: byt till aiosqlite — ingen annan ändring behövs     │
# │ • Cypress använder detta för att verifiera skapade trans.  │
# └──────────────────────────────────────────────────────────────┘
@app.route('/transactions/<transaction_id>')
async def get_transaction(request, transaction_id):
    # ⚠️ SYNKRON DB-anslutning — blockerar event loopen ~1ms per anrop
    # Inte kritiskt tidsmässigt, men principiellt — bör vara async
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Söker på PRIMARY KEY — snabb lookup O(log N) redan utan extra index
        cursor.execute(
            'SELECT transaction_id, account_id, amount FROM transactions WHERE transaction_id = ?',
            (transaction_id,)
        )
        # fetchone() returnerar en tupel eller None om inget hittades
        transaction = cursor.fetchone()

        # 404 om transaktionen inte finns
        if not transaction:
            return json({'error': 'Transaction not found'}, status=404)

        # Bygg dict med namngivna fält
        result = {
            'transaction_id': str(transaction[0]),
            'account_id': transaction[1],
            'amount': transaction[2]
        }
        return json(result)


# === ENDPOINT: GET /accounts/count ===
# Hämta antal unika konton + lista med deras ID:n (extra feature)
# ┌──────────────────────────────────────────────────────────────┐
# │ OPTIMERINGSANALYS:                                          │
# │ • DISTINCT account_id = full table scan O(N) oavsett INDEX  │
# │   (INDEX hjälper dock — SQLite kan scanna indexet istället  │
# │   för hela tabellen, vilket är kompaktare och snabbare)     │
# │ • Med 50 000 rader → ~50ms scan + sort                     │
# │ • Alternativ: COUNT(DISTINCT account_id) i SQL istället    │
# │   för att ladda alla i Python-minnet                        │
# │ • Sync sqlite3 = blockerar event loopen under hela scanen  │
# └──────────────────────────────────────────────────────────────┘
@app.route('/accounts/count')
async def get_account_count(request):
    # ⚠️ SYNKRON — DISTINCT kräver full scan av tabellen O(N)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # DISTINCT = unika värden — SQLite måste läsa alla rader
        cursor.execute('SELECT DISTINCT account_id FROM transactions')
        # List comprehension — extrahera account_id från varje rad-tupel
        accounts = [row[0] for row in cursor.fetchall()]
    # Returnera antal + listan
    return json({'count': len(accounts), 'account_ids': accounts})


# === ENDPOINT: GET /accounts/<account_id> ===
# Beräkna kontots saldo genom att summera alla transaktioner
# ┌──────────────────────────────────────────────────────────────┐
# │ OPTIMERINGSANALYS:                                          │
# │ • SUM(amount) WHERE account_id = ? → aggregering           │
# │ • Utan INDEX: full table scan O(N) = läser ALLA 50 000     │
# │   rader för att hitta de ~50 som tillhör kontot             │
# │ • Med INDEX: O(log N) lookup + O(K) summering av K rader   │
# │   K = antal transaktioner för kontot (typiskt 50-100)       │
# │ • Gör dessutom TVÅ queries: SUM + SELECT 1 (existenskoll)  │
# │   Möjlig optimering: slå ihop till EN query med COALESCE    │
# │     SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM ...      │
# │   Om COUNT=0 → kontot existerar inte → 404                 │
# │ • Cypress testar denna endpoint — response-format kritiskt │
# └──────────────────────────────────────────────────────────────┘
@app.route('/accounts/<account_id>')
async def get_account(request, account_id):
    # ⚠️ SYNKRON — SUM kräver scan av alla rader för kontot
    # Utan INDEX: O(N) full table scan = 50 000 radjämförelser
    # Med INDEX: O(log N + K) = ~17 trädnoder + 50 rader = blixtsnabbt
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Beräkna saldo direkt i SQL — summera alla belopp för kontot
        cursor.execute(
            'SELECT SUM(amount) FROM transactions WHERE account_id = ?',
            (account_id,)
        )
        # fetchone()[0] = summan, eller None om inga rader → default 0
        balance = cursor.fetchone()[0] or 0

        # Kontrollera att kontot faktiskt existerar (har minst en transaktion)
        # LIMIT 1 = stoppa efter första träffen (snabbt)
        cursor.execute(
            'SELECT 1 FROM transactions WHERE account_id = ? LIMIT 1',
            (account_id,)
        )
        # Om ingen rad hittades → kontot existerar inte
        if not cursor.fetchone():
            return json({'error': 'Account not found'}, status=404)

        # Returnera kontot med beräknad balans
        return json({
            'account_id': account_id,
            'balance': balance
        })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
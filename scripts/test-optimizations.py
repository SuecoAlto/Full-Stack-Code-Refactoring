"""
test-optimizations.py — Testverktyg som mäter serverns prestanda.

VAD:
  Kör 7 olika tester som mäter hur bra (eller dåligt) servern presterar.
  Tänk på det som en "hälsokontroll" — den avslöjar exakt vilka
  optimeringar som saknas och visar PASS/FAIL för varje.

HUR:
  Skickar HTTP-anrop till servern (localhost:8000) och mäter:
  - Svarstider (hur snabbt servern svarar)
  - Felfrekvens (hur många anrop som misslyckas)
  - Parallellism (kan servern hantera flera anrop samtidigt?)
  - Databasstruktur (har SQLite ett index eller söker den linjärt?)

VARFÖR:
  Utan mätningar vet man inte OM optimeringarna gör skillnad.
  Kör scriptet FÖRE och EFTER dina ändringar → se förbättringen i siffror.
  Perfekt för att bevisa i PR-review att optimeringarna faktiskt fungerar.

DE 7 TESTERNA:
  Test 1: Event loop blocking
    "Fryser servern när den jobbar med databasen?"
    Skickar tunga DB-anrop + lätta /ping samtidigt.
    Om /ping är långsam → event loopen är blockerad av sync sqlite3.

  Test 2: Database locked
    "Kraschar servern vid många samtidiga skrivningar?"
    Skickar 200 POST-requests på en gång.
    Utan WAL-mode → databasen låser sig → 500-fel.

  Test 3: Query performance
    "Hur snabbt hittar databasen data för ett specifikt konto?"
    Mäter svarstid för SUM(amount) och filtrerade transaktioner.
    Utan INDEX → full tabellscan, långsamt.

  Test 4: Throughput
    "Hur många anrop per sekund klarar servern?"
    Skickar 500 anrop och mäter total tid.
    Mål: >1000 req/s.

  Test 5: Query plan (DIREKT mot databasen — ingen server behövs)
    "Söker SQLite linjärt eller via index?"
    Kör EXPLAIN QUERY PLAN — SQLites egna analysverktyg.
    SCAN = dåligt (läser alla rader), INDEX = bra (hoppar direkt).

  Test 6: Race condition
    "Förlorar servern data vid samtidiga skrivningar?"
    Skickar 200 identiska POST-requests och kontrollerar att
    ALLA sparades i databasen med rätt totalbelopp.

  Test 7: Async parallelism
    "Kan servern göra flera saker samtidigt?"
    Jämför sekventiell vs parallell hastighet.
    Med sync sqlite3: parallell ≈ sekventiell (allt blockeras).
    Med aiosqlite: parallell << sekventiell (äkta parallellism).

BEROENDEN:
  ┌─────────────────────────────────────────────────────────────┐
  │ test-optimizations.py                                       │
  │   │                                                         │
  │   ├── HTTP → localhost:8000 (server.py måste vara igång)    │
  │   │   └── Test 1, 2, 3, 4, 6, 7                            │
  │   │                                                         │
  │   ├── sqlite3 → ../app-sanic/transactions.db (direkt)      │
  │   │   └── Test 5 (query plan) + Test 6 (cleanup + verify)  │
  │   │                                                         │
  │   └── pip install aiohttp (async HTTP-klient)               │
  └─────────────────────────────────────────────────────────────┘

  Kräver att servern körs: sanic server.app (port 8000)
  Kräver att databasen har data: python populate-db.py

BEHÖVER JAG ÄNDRA DENNA FIL?
  Nej — detta är ett testverktyg som VERIFIERAR dina optimeringar.
  Du ändrar server.py, sedan kör du detta skript för att se om det blev
  bättre. Testerna själva behöver inte modifieras.
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORTS — verktyg som scriptet behöver
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# asyncio: Pythons inbyggda verktyg för att köra saker "samtidigt" (asynkront)
# Tänk: en kock som kan starta 100 beställningar utan att vänta på att varje ska bli klar
import asyncio
# aiohttp: HTTP-klient som kan skicka många HTTP-anrop parallellt (async)
# Tänk: istället för att ringa en person åt gången, ringer du alla 200 samtidigt
import aiohttp
# sqlite3: direkt databasåtkomst (för Test 5 och Test 6 som pratar med DB utan servern)
import sqlite3
# time: tidtagning — time.monotonic() ger exakt tid i sekunder
import time
# statistics: matematiska funktioner — median (mittenvärdet), inte påverkad av extremvärden
import statistics

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# KONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Adressen till servern — alla HTTP-anrop går hit
API_URL = 'http://localhost:8000'
# Antal samtidiga anrop i stresstesterna (Test 2)
# 200 = realistiskt högt tryck — räcker för att avslöja problem
CONCURRENT = 200

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HJÄLPFUNKTION — tidmätning av HTTP-anrop
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def timed_request(session, method, url, **kwargs):
    """Skicka ett HTTP-anrop och mät hur lång tid det tar.

    Tänk: du startar ett tidtagarur, skickar anropet, väntar på svar,
    och stoppar uret. Returnerar (statuskod, tid_i_millisekunder).
    Statuskod 200/201 = OK, 500 = serverfel, 0 = kunde inte nå servern.
    """
    # Starta tidtagningen — monotonic() kan inte gå bakåt (pålitligare än time())
    start = time.monotonic()
    try:
        # Skicka HTTP-anropet (GET, POST, etc.) och vänta på svar
        # "async with" = öppna anslutning, gör anropet, stäng anslutningen
        async with session.request(method, url, **kwargs) as resp:
            # Läs hela svaret (måste göras innan anslutningen stängs)
            await resp.read()
            # Returnera statuskoden och tiden i millisekunder
            # (time.monotonic() - start) = sekunder, × 1000 = millisekunder
            return resp.status, (time.monotonic() - start) * 1000
    except Exception as e:
        # Om servern inte svarar (nede, timeout, etc.) → statuskod 0
        return 0, (time.monotonic() - start) * 1000


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 1: Fryser servern när databasen jobbar?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_event_loop_blocking():
    """Test 1: Event loop blocking.

    ANALOGI: Tänk dig en receptionist som OCKSÅ måste hämta paket på lagret.
    Med sync sqlite3: Receptionisten går till lagret och ALLA som ringer
    får vänta tills hen kommer tillbaka. Ingen svarar i telefonen.
    Med aiosqlite: Receptionisten skickar en assistent till lagret och
    fortsätter svara i telefonen medan assistenten jobbar.

    Så här fungerar testet:
    1. Skicka 50 tunga anrop (GET /transactions = hämta alla 50 000 rader)
    2. Skicka 50 lätta anrop (GET /ping = "lever du?") SAMTIDIGT
    3. Mät hur lång tid /ping tar

    Om /ping tar >100ms → servern är blockerad (sync DB fryser event loopen)
    Om /ping tar <50ms → servern hanterar tunga och lätta anrop parallellt
    """
    # Skriv ut testets rubrik
    print('=' * 60)
    print('TEST 1: Event loop blocking')
    print('=' * 60)
    print('Sending 50 heavy DB requests + 50 /ping requests simultaneously...')
    print('If the event loop is blocked, /ping will be slow.\n')

    # Skapa en HTTP-session (återanvänder anslutningar = snabbare)
    # "async with" = stänger sessionen automatiskt när vi är klara
    async with aiohttp.ClientSession() as session:
        # Skapa 50 tunga anrop — varje hämtar ALLA transaktioner (50 000 rader)
        # Dessa tar lång tid och belastar databasen
        heavy_tasks = [timed_request(session, 'GET', f'{API_URL}/transactions') for _ in range(50)]
        # Skapa 50 lätta anrop — /ping returnerar bara {"result":"pong"}
        # Dessa BÖR vara snabba om servern inte är blockerad
        ping_tasks = [timed_request(session, 'GET', f'{API_URL}/ping') for _ in range(50)]

        # Slå ihop till en lista och kör ALLA 100 anrop SAMTIDIGT
        # asyncio.gather() = "starta allt, vänta tills allt är klart"
        all_tasks = heavy_tasks + ping_tasks
        results = await asyncio.gather(*all_tasks)

    # Dela upp resultaten: de första 50 = tunga, de sista 50 = /ping
    # r[1] = tiden i millisekunder (vi bryr oss inte om statuskoden här)
    heavy_times = [r[1] for r in results[:50]]
    ping_times = [r[1] for r in results[50:]]

    # Skriv ut statistik för tunga anrop
    print(f'  /transactions (heavy):')
    # Median = mittenvärdet (bättre än medelvärde — påverkas inte av extremvärden)
    print(f'    Median: {statistics.median(heavy_times):.0f}ms')
    # P95 = den 95:e percentilen — "95% av anropen var snabbare än detta"
    print(f'    P95:    {sorted(heavy_times)[int(len(heavy_times)*0.95)]:.0f}ms')
    # Max = det absolut långsammaste anropet
    print(f'    Max:    {max(heavy_times):.0f}ms')

    # Spara /ping-medianen — detta är nyckelsvaret för testet
    ping_median = statistics.median(ping_times)
    print(f'  /ping (should be <50ms if event loop is free):')
    print(f'    Median: {ping_median:.0f}ms')
    print(f'    P95:    {sorted(ping_times)[int(len(ping_times)*0.95)]:.0f}ms')
    print(f'    Max:    {max(ping_times):.0f}ms')

    # Visa PASS/FAIL mot målen
    print(f'\n  Benchmark targets:')
    print(f'    /ping median < 50ms:  {"PASS" if ping_median < 50 else "FAIL"} (got {ping_median:.0f}ms)')
    print(f'    /ping median < 100ms: {"PASS" if ping_median < 100 else "FAIL"} (got {ping_median:.0f}ms)')

    # Slutgiltig bedömning
    if ping_median > 100:
        print('\n  VERDICT: FAIL — event loop is blocked by sync DB calls')
    else:
        print('\n  VERDICT: PASS — event loop is not blocked')
    print()

    # Returnera resultaten som en dict — används av sammanfattningen i main()
    return {
        'ping_median': ping_median,
        'heavy_median': statistics.median(heavy_times),
        'passed': ping_median < 100
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 2: Kraschar databasen vid hög belastning?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_database_locked():
    """Test 2: Database locked errors under high concurrency.

    ANALOGI: Tänk dig en toalett med ETT lås (default SQLite journal mode).
    Om 200 personer försöker gå in samtidigt → bara en kommer in,
    resten får felmeddelande "upptagen!".

    Med WAL-mode: toaletten har SEPARATA avdelningar — en för läsning
    och en för skrivning. Flera kan läsa samtidigt, och skrivare
    blockerar inte läsare.

    Testet skickar 200 POST-requests (skrivoperationer) SAMTIDIGT.
    Utan WAL: många misslyckas med "database is locked" → HTTP 500.
    Med WAL: alla 200 ska lyckas (HTTP 201).
    """
    print('=' * 60)
    print('TEST 2: Database locked errors (high concurrency)')
    print('=' * 60)
    print(f'Sending {CONCURRENT} concurrent POST requests...\n')

    # Testkonto-ID — används bara för detta test
    account_id = 'test-locked-check'

    # Skapa HTTP-session och förbered 200 parallella POST-anrop
    async with aiohttp.ClientSession() as session:
        # Skapa en lista med 200 uppgifter — varje skapar en transaktion
        # json={...} = skicka JSON-body med konto-ID och belopp
        tasks = [
            timed_request(session, 'POST', f'{API_URL}/transactions',
                         json={'account_id': account_id, 'amount': 1})
            for _ in range(CONCURRENT)
        ]
        # Kör alla 200 POST-anrop SAMTIDIGT och vänta på alla svar
        results = await asyncio.gather(*tasks)

    # Dela upp resultaten i statuskoder och tider
    statuses = [r[0] for r in results]   # Lista med alla statuskoder (201, 500, 0...)
    times = [r[1] for r in results]       # Lista med alla svarstider i ms
    success = statuses.count(201)         # Räkna lyckade (201 = Created)
    errors = len(statuses) - success      # Resten = fel (500, timeout, etc.)

    # Mät mediansvarstiden
    median_time = statistics.median(times)
    print(f'  Successful (201): {success}')
    print(f'  Errors:           {errors}')
    print(f'  Response times:')
    print(f'    Median: {median_time:.0f}ms')
    print(f'    P95:    {sorted(times)[int(len(times)*0.95)]:.0f}ms')
    print(f'    Max:    {max(times):.0f}ms')

    # Visa PASS/FAIL
    print(f'\n  Benchmark targets:')
    print(f'    0 errors:           {"PASS" if errors == 0 else "FAIL"} (got {errors})')
    print(f'    Median < 200ms:     {"PASS" if median_time < 200 else "FAIL"} (got {median_time:.0f}ms)')

    if errors > 0:
        print(f'\n  VERDICT: FAIL — {errors} requests failed (likely "database is locked")')
    else:
        print('\n  VERDICT: PASS — all requests succeeded')
    print()

    # Returnera resultat till main()
    return {
        'successes': success,
        'errors': errors,
        'median_ms': median_time,
        'passed': errors == 0
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 3: Hur snabbt hittar databasen kontosdata?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_query_performance():
    """Test 3: Query performance for account-specific requests.

    ANALOGI: Tänk dig en telefonbok med 50 000 namn.
    Utan INDEX: Du bläddrar från sida 1 till 50 000 för att hitta "Svensson".
    Med INDEX: Du slår upp "S" i registret och hoppar direkt till rätt sida.

    Testet mäter svarstiden för:
    - GET /accounts/account1 → SUM(amount) WHERE account_id = 'account1'
    - GET /transactions?account_id=account1 → alla transaktioner för kontot

    Utan INDEX: 50 000 radjämförelser per anrop.
    Med INDEX: ~17 trädjämförelser (B-tree) + ~10 000 rader för ett konto.
    """
    print('=' * 60)
    print('TEST 3: Query performance (index effectiveness)')
    print('=' * 60)
    print('Measuring response times for account-specific queries...\n')

    # Testa med account1 — har ~10 000 transaktioner i testdatan
    account_id = 'account1'

    async with aiohttp.ClientSession() as session:
        # "Warm up" — första anropet kan vara långsammare (cache-kall)
        # Vi kastar bort resultatet — syftet är bara att värma upp servern
        await timed_request(session, 'GET', f'{API_URL}/accounts/{account_id}')

        # Mät GET /accounts/account1 — beräknar saldo via SUM(amount)
        # 20 anrop ger pålitlig statistik (en enda mätning kan variera)
        balance_tasks = [
            timed_request(session, 'GET', f'{API_URL}/accounts/{account_id}')
            for _ in range(20)
        ]
        # Kör alla 20 parallellt och samla svaren
        balance_results = await asyncio.gather(*balance_tasks)

        # Mät GET /transactions?account_id=account1 — hämtar filtrerade rader
        filter_tasks = [
            timed_request(session, 'GET', f'{API_URL}/transactions?account_id={account_id}')
            for _ in range(20)
        ]
        filter_results = await asyncio.gather(*filter_tasks)

    # Extrahera tiderna (index [1] i varje resultat-tupel)
    balance_times = [r[1] for r in balance_results]
    filter_times = [r[1] for r in filter_results]
    # Beräkna medianer — mittenvärdet av tiderna
    balance_median = statistics.median(balance_times)
    filter_median = statistics.median(filter_times)

    # Skriv ut resultat
    print(f'  GET /accounts/{account_id} (balance via SUM):')
    print(f'    Median: {balance_median:.1f}ms')
    print(f'    Max:    {max(balance_times):.1f}ms')
    print(f'  GET /transactions?account_id={account_id} (filtered):')
    print(f'    Median: {filter_median:.1f}ms')
    print(f'    Max:    {max(filter_times):.1f}ms')

    # PASS/FAIL mot mål
    # 20ms för SUM = rimligt med INDEX (utan: ~100-200ms)
    # 100ms för filtrering = rimligt (returnerar ~10 000 rader som JSON)
    print(f'\n  Benchmark targets:')
    print(f'    Balance median < 20ms:     {"PASS" if balance_median < 20 else "FAIL"} (got {balance_median:.1f}ms)')
    print(f'    Filter median < 100ms:     {"PASS" if filter_median < 100 else "FAIL"} (got {filter_median:.1f}ms)')

    # Båda måste passera för att testet ska lyckas
    all_pass = balance_median < 20 and filter_median < 100
    print(f'\n  VERDICT: {"PASS" if all_pass else "FAIL"} — {"queries are fast" if all_pass else "queries are slow, add index on account_id"}')
    print()

    return {
        'balance_median': balance_median,
        'filter_median': filter_median,
        'passed': all_pass
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 4: Hur många anrop per sekund klarar servern?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_throughput():
    """Test 4: Overall throughput (requests per second).

    ANALOGI: Tänk dig en kassakö.
    Throughput = hur många kunder som betjänas per minut.
    Med sync DB = en kassörska som går till lagret för varje vara.
    Med async DB = kassörskan ber någon annan hämta medan hon scannar nästa.

    Skickar 500 POST-requests (skapar transaktioner) och mäter total tid.
    req/s = antal lyckade / total tid i sekunder.
    Mål: >1000 req/s (bra), >2000 req/s (utmärkt).
    """
    print('=' * 60)
    print('TEST 4: Throughput (requests/second)')
    print('=' * 60)

    # Antal anrop att skicka
    num_requests = 500
    # Testkonto — separerar testdata från riktiga data
    account_id = 'throughput-test'

    print(f'Sending {num_requests} sequential POST requests...\n')

    async with aiohttp.ClientSession() as session:
        # Starta tidtagningen INNAN alla anrop
        start = time.monotonic()
        # Skapa 500 POST-uppgifter — alla körs parallellt
        tasks = [
            timed_request(session, 'POST', f'{API_URL}/transactions',
                         json={'account_id': account_id, 'amount': 1})
            for _ in range(num_requests)
        ]
        # Kör alla 500 och vänta tills alla är klara
        results = await asyncio.gather(*tasks)
        # Stoppa klockan — total tid i sekunder
        elapsed = time.monotonic() - start

    # Räkna lyckade anrop (201 = Created)
    success = sum(1 for r in results if r[0] == 201)
    # requests per second = lyckade anrop / tid
    rps = success / elapsed

    print(f'  Total time:    {elapsed:.2f}s')
    print(f'  Successful:    {success}/{num_requests}')
    print(f'  Throughput:    {rps:.0f} req/s')

    # Visa PASS/FAIL mot tre nivåer
    print(f'\n  Benchmark targets:')
    print(f'    > 500 req/s:   {"PASS" if rps > 500 else "FAIL"} (got {rps:.0f})')
    print(f'    > 1000 req/s:  {"PASS" if rps > 1000 else "FAIL"} (got {rps:.0f})')
    print(f'    > 2000 req/s:  {"PASS" if rps > 2000 else "FAIL"} (got {rps:.0f})')

    print(f'\n  VERDICT: {"PASS" if rps > 1000 else "FAIL"}')
    print()

    return {
        'rps': rps,
        'passed': rps > 1000
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 5: Söker databasen linjärt eller via index?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_query_plan():
    """Test 5: Query plan analysis — PRATAR DIREKT MED DATABASEN (ingen server behövs).

    ANALOGI: Tänk dig att du frågar en bibliotekarie "hur letar du efter en bok?"
    EXPLAIN QUERY PLAN = bibliotekariens svar om HUR hen söker.
    "SCAN TABLE" = "Jag går genom VARJE hylla tills jag hittar den" (långsamt)
    "USING INDEX" = "Jag kollar registret och går direkt till rätt hylla" (snabbt)

    Detta test kopplar DIREKT till transactions.db (inte via servern)
    och frågar SQLite: "Om jag söker på account_id, hur gör du?"
    SQLite svarar med sin plan — och vi kollar om den använder INDEX.
    """
    print('=' * 60)
    print('TEST 5: Query plan (SCAN vs INDEX)')
    print('=' * 60)
    print('Checking if SQLite uses an index for account_id queries...\n')

    # Sökväg till databasen — relativ från scripts/ (vi kör scriptet därifrån)
    db_path = '../app-sanic/transactions.db'
    try:
        # Öppna databasanslutning direkt (inte via servern)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Definiera de queries vi vill analysera
        # Varje entry: 'beskrivning': ('SQL-sats', (parametrar,))
        queries = {
            # Query 1: Filtrera transaktioner per konto
            'WHERE account_id = ?': ('SELECT * FROM transactions WHERE account_id = ?', ('account1',)),
            # Query 2: Beräkna saldo (SUM) per konto
            'SUM by account_id':   ('SELECT SUM(amount) FROM transactions WHERE account_id = ?', ('account1',)),
        }

        # Anta att alla har INDEX tills vi hittar en som inte har det
        all_indexed = True
        for label, (sql, params) in queries.items():
            # EXPLAIN QUERY PLAN = fråga SQLite "hur tänker du göra detta?"
            # Returnerar t.ex. [(0, 0, 0, 'SCAN TABLE transactions')]
            # eller [(0, 0, 0, 'SEARCH TABLE transactions USING INDEX idx_account_id')]
            cursor.execute(f'EXPLAIN QUERY PLAN {sql}', params)
            plan = cursor.fetchall()
            # Konvertera till sträng för enkel sökning
            plan_str = str(plan)
            # Kolla om svaret innehåller "USING INDEX" — det betyder att SQLite
            # använder indexet istället för att läsa alla rader
            uses_index = 'USING INDEX' in plan_str or 'USING COVERING INDEX' in plan_str
            status = 'PASS (uses INDEX)' if uses_index else 'FAIL (full SCAN)'
            print(f'  {label}:')
            print(f'    Plan: {plan_str}')
            print(f'    {status}')
            # Om någon query INTE använder INDEX → testet misslyckas
            if not uses_index:
                all_indexed = False

        # Stäng databasanslutningen
        conn.close()

        print(f'\n  VERDICT: {"PASS" if all_indexed else "FAIL"} — {"all queries use index" if all_indexed else "add INDEX on account_id"}')
        return {'indexed': all_indexed, 'passed': all_indexed}
    except Exception as e:
        # Om databasen inte finns eller inte kan öppnas
        print(f'  Could not open database: {e}')
        print(f'  Make sure {db_path} exists (run populate-db.py first)')
        return {'indexed': False, 'passed': False}
    finally:
        # Skriv alltid en tom rad efter testet (oavsett om det lyckades)
        print()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 6: Förlorar servern data vid samtidiga skrivningar?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_race_condition():
    """Test 6: Race condition / data integrity.

    ANALOGI: Tänk dig att 200 personer sätter in 1 kr var till samma konto.
    Saldot borde bli exakt 200 kr. Men om servern tappar bort insättningar
    (race condition) kanske saldot blir 180 eller 195.

    Testet:
    1. Rensar gammalt testdata från databasen
    2. Skickar 200 POST-requests (1 kr vardera) SAMTIDIGT till SAMMA konto
    3. Kollar i databasen:
       - Finns alla 200 transaktioner? (ingen tappades bort)
       - Är saldot exakt 200? (ingen dubbelbokades eller försvann)
    """
    print('=' * 60)
    print('TEST 6: Race condition (data integrity)')
    print('=' * 60)

    # Unikt konto-ID bara för detta test — blandas inte med andra data
    account_id = 'race-condition-test'
    num_requests = 200
    # Varje transaktion sätter in 1 kr
    amount = 1

    # ── Steg 1: Rensa gammalt testdata ──────────────────────────
    # Om testet körts förut finns det gamla rader med samma account_id
    # Vi raderar dem så vi börjar från 0
    db_path = '../app-sanic/transactions.db'
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # DELETE = radera alla rader som matchar account_id
        cursor.execute('DELETE FROM transactions WHERE account_id = ?', (account_id,))
        # Spara raderingen
        conn.commit()
        conn.close()
    except Exception:
        # Om databasen inte finns/kan öppnas — ignorera, testet kommer ändå misslyckas
        pass

    print(f'  Sending {num_requests} concurrent POST requests to same account...\n')

    # ── Steg 2: Skicka 200 POST-requests SAMTIDIGT ─────────────
    async with aiohttp.ClientSession() as session:
        tasks = [
            timed_request(session, 'POST', f'{API_URL}/transactions',
                         json={'account_id': account_id, 'amount': amount})
            for _ in range(num_requests)
        ]
        # Alla 200 körs parallellt — om servern har problem förlorar den data
        results = await asyncio.gather(*tasks)

    # Vänta lite — ge databasen tid att skriva klart (disk-flush)
    await asyncio.sleep(0.5)

    # ── Steg 3: Räkna lyckade/misslyckade HTTP-svar ──────────
    successes = sum(1 for r in results if r[0] == 201)  # 201 = Created
    errors = sum(1 for r in results if r[0] != 201)      # Allt annat = fel

    # ── Steg 4: Verifiera DIREKT i databasen ────────────────
    # Vi pratar direkt med DB istället för via servern — helt säkert
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    # Räkna hur många rader som faktiskt sparades
    cursor.execute('SELECT COUNT(*) FROM transactions WHERE account_id = ?', (account_id,))
    count = cursor.fetchone()[0]  # [0] = första kolumnen i första raden
    # Beräkna totalt insatt belopp
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE account_id = ?', (account_id,))
    balance = cursor.fetchone()[0] or 0  # or 0 = om inga rader: None → 0
    conn.close()

    # Förväntat saldo = antal lyckade × belopp per transaktion
    # Om 200 lyckades och varje satte in 1 kr → förväntat = 200
    expected_balance = successes * amount

    # Skriv ut vad som hände
    print(f'  HTTP 201 responses:  {successes}')
    print(f'  HTTP errors:         {errors}')
    print(f'  Transactions in DB:  {count}')
    print(f'  Expected balance:    {expected_balance}')
    print(f'  Actual balance:      {balance}')

    # PASS/FAIL
    print(f'\n  Benchmark targets:')
    print(f'    0 HTTP errors:      {"PASS" if errors == 0 else "FAIL"} (got {errors})')
    # count ska matcha successes — varje lyckat POST bör ha skapat en rad
    print(f'    All writes saved:   {"PASS" if count == successes else "FAIL"} (got {count}/{successes})')
    # Saldot ska vara exakt korrekt — inget tappar eller dubbleras
    print(f'    Balance correct:    {"PASS" if balance == expected_balance else "FAIL"} (got {balance}, expected {expected_balance})')

    # Alla tre villkor måste vara uppfyllda
    data_ok = errors == 0 and count == successes and balance == expected_balance
    print(f'\n  VERDICT: {"PASS" if data_ok else "FAIL"} — {"no data lost" if data_ok else "DATA INTEGRITY ISSUE"}')
    print()

    return {
        'errors': errors,
        'count': count,
        'expected': successes,
        'balance_ok': balance == expected_balance,
        'passed': data_ok
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TEST 7: Kan servern göra saker parallellt?
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_async_parallelism():
    """Test 7: Async parallelism — sequential vs parallel.

    ANALOGI: Du ska skicka 10 brev.
    Sekventiellt: gå till brevlådan, posta, gå tillbaka, ta nästa brev. Upprepa.
    Parallellt: ge alla 10 brev till 10 kompisar och säg "gå alla nu".

    Om servern blockeras av sync sqlite3: parallellt tar LIKA lång tid som
    sekventiellt, dvs ratio ≈ 1.0x (ingen vinst). Allt körs ändå i sekvens
    internt.

    Med aiosqlite: parallellt tar en BRÅKDEL av sekventiellt.
    Ratio > 2.0x = servern gör saker asynkront (bra).
    Ratio > 5.0x = utmärkt — nästan linjär parallelism.
    """
    print('=' * 60)
    print('TEST 7: Async parallelism (sequential vs parallel)')
    print('=' * 60)

    # 10 tunga anrop — tillräckligt för att se mönstret
    num_requests = 10
    print(f'  Sending {num_requests} heavy GET /transactions requests...\n')

    async with aiohttp.ClientSession() as session:
        # ── Sekventiell körning: ett anrop i taget ──────────────
        # "await" = vänta tills detta anrop är klart INNAN nästa startas
        seq_start = time.monotonic()
        for _ in range(num_requests):
            await timed_request(session, 'GET', f'{API_URL}/transactions')
        # Total tid = summan av alla 10 anropens tid (de körs en efter en)
        seq_time = (time.monotonic() - seq_start) * 1000

        # ── Parallell körning: alla anrop samtidigt ─────────────
        # Alla 10 startas DIREKT, sedan väntar vi tills den SISTA är klar
        par_start = time.monotonic()
        tasks = [timed_request(session, 'GET', f'{API_URL}/transactions') for _ in range(num_requests)]
        await asyncio.gather(*tasks)
        # Total tid ≈ det LÄNGSTA ENSKILDA anropet (inte summan)
        par_time = (time.monotonic() - par_start) * 1000

    # Beräkna speedup-ratio: sekventiell tid / parallell tid
    # Ratio 1.0 = ingen skillnad (servern blockerar)
    # Ratio 5.0 = parallell är 5x snabbare (äkta asynk)
    ratio = seq_time / par_time if par_time > 0 else 0
    # Ratio > 2.0 = servern hanterar requests parallellt
    is_parallel = ratio > 2.0

    print(f'  Sequential ({num_requests} requests): {seq_time:.0f}ms')
    print(f'  Parallel   ({num_requests} requests): {par_time:.0f}ms')
    print(f'  Speedup ratio:  {ratio:.1f}x')

    # PASS/FAIL mot mål
    print(f'\n  Benchmark targets:')
    print(f'    Ratio > 2.0x (true parallelism): {"PASS" if is_parallel else "FAIL"} (got {ratio:.1f}x)')
    print(f'    Ratio > 5.0x (excellent):        {"PASS" if ratio > 5.0 else "FAIL"} (got {ratio:.1f}x)')

    if is_parallel:
        print(f'\n  VERDICT: PASS — server handles requests in parallel (async DB)')
    else:
        print(f'\n  VERDICT: FAIL — requests are serialized (sync DB blocks event loop)')
    print()

    return {
        'seq_ms': seq_time,
        'par_ms': par_time,
        'ratio': ratio,
        'passed': is_parallel
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN — kör alla 7 tester och visa sammanfattning
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def main():
    """Huvudfunktion som kör alla tester i ordning och sammanfattar resultaten.

    Varje test returnerar en dict med mätvärden och 'passed': True/False.
    I slutet visas:
    1. Resultattabell (PASS/FAIL per test)
    2. Self-review (dynamiska rekommendationer baserat på uppmätta värden)
    3. Big-O tabell (teoretisk + uppmätt komplexitet)
    """
    print()
    print('OPTIMIZATION TEST SUITE')
    print('Run before and after changes to compare.')
    print()

    # Kör alla 7 tester och spara resultaten
    # Test 1-4, 6, 7: kräver servern (async → await)
    # Test 5: pratar direkt med databasen (synkron → inget await)
    r1 = await test_event_loop_blocking()
    r2 = await test_database_locked()
    r3 = await test_query_performance()
    r4 = await test_throughput()
    r5 = test_query_plan()                 # ← enda synkrona testet (direkt DB-åtkomst)
    r6 = await test_race_condition()
    r7 = await test_async_parallelism()

    # ── Sammanfattningstabell ───────────────────────────────────
    # Bygg en lista med (testnamn, pass/fail, detaljer) för snygg utskrift
    results = [
        ('T1 Event loop blocking', r1['passed'], f"/ping median {r1['ping_median']:.0f}ms (target <100ms)"),
        ('T2 Database locked',     r2['passed'], f"{r2['errors']} errors, median {r2['median_ms']:.0f}ms"),
        ('T3 Query performance',   r3['passed'], f"balance {r3['balance_median']:.1f}ms, filter {r3['filter_median']:.1f}ms"),
        ('T4 Throughput',          r4['passed'], f"{r4['rps']:.0f} req/s (target >1000)"),
        ('T5 Query plan (INDEX)',  r5['passed'], f"{'uses INDEX' if r5['indexed'] else 'full SCAN'}"),
        ('T6 Race condition',      r6['passed'], f"{r6['count']}/{r6['expected']} saved, balance {'OK' if r6['balance_ok'] else 'WRONG'}"),
        ('T7 Async parallelism',   r7['passed'], f"speedup {r7['ratio']:.1f}x (target >2.0x)"),
    ]

    # Räkna antal godkända tester
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)

    # Skriv ut sammanfattningstabell
    print('=' * 60)
    print(f'RESULTS: {passed}/{total} PASSED')
    print('=' * 60)
    for name, ok, detail in results:
        icon = 'PASS' if ok else 'FAIL'
        # Varje rad visar [PASS] eller [FAIL] + testnamn + uppmätt värde
        print(f'  [{icon}] {name}: {detail}')
    print('=' * 60)

    # ── Self-review — dynamiska rekommendationer ─────────────
    # Baserat på FAKTISKA mätresultat (inte teori) — visar exakt vad som
    # behöver fixas och vad som redan fungerar
    print()
    print('=' * 60)
    print('SELF-REVIEW NOTES (based on measured results)')
    print('=' * 60)

    # Kontrollera aiosqlite (Test 1 + Test 7 mäter detta)
    if not r1['passed'] or not r7['passed']:
        print(f"\n  [NEEDS FIX] Async DB (aiosqlite)")
        print(f"    /ping blocked at {r1['ping_median']:.0f}ms (should be <100ms)")
        print(f"    Parallelism ratio {r7['ratio']:.1f}x (should be >2.0x)")
        print(f"    → Switch sqlite3 → aiosqlite to unblock the event loop")
    else:
        print(f"\n  [OK] Async DB — event loop free ({r1['ping_median']:.0f}ms), parallelism {r7['ratio']:.1f}x")

    # Kontrollera INDEX (Test 5 + Test 3 mäter detta)
    if not r5['passed'] or not r3['passed']:
        print(f"\n  [NEEDS FIX] INDEX on account_id")
        print(f"    Query plan: {'full SCAN' if not r5['indexed'] else 'INDEX'}")
        print(f"    Balance query: {r3['balance_median']:.1f}ms (target <20ms)")
        print(f"    Filter query:  {r3['filter_median']:.1f}ms (target <100ms)")
        print(f"    → CREATE INDEX idx_account_id ON transactions(account_id)")
    else:
        print(f"\n  [OK] INDEX — balance {r3['balance_median']:.1f}ms, filter {r3['filter_median']:.1f}ms")

    # Kontrollera WAL-mode (Test 2 mäter detta)
    if not r2['passed']:
        print(f"\n  [NEEDS FIX] WAL mode for concurrent writes")
        print(f"    {r2['errors']} errors out of {CONCURRENT} concurrent POSTs")
        print(f"    → PRAGMA journal_mode=WAL at startup")
    else:
        print(f"\n  [OK] Concurrent writes — 0 errors at {CONCURRENT} concurrent POSTs")

    # Kontrollera throughput (Test 4 mäter detta)
    if not r4['passed']:
        print(f"\n  [NEEDS FIX] Throughput too low")
        print(f"    Current: {r4['rps']:.0f} req/s (target >1000)")
        print(f"    → Combine aiosqlite + WAL + INDEX for higher throughput")
    else:
        print(f"\n  [OK] Throughput — {r4['rps']:.0f} req/s")

    # Kontrollera data integrity (Test 6 mäter detta)
    if not r6['passed']:
        print(f"\n  [NEEDS FIX] Data integrity under concurrency")
        print(f"    {r6['count']}/{r6['expected']} transactions saved")
        print(f"    Balance correct: {r6['balance_ok']}")
    else:
        print(f"\n  [OK] Data integrity — {r6['count']}/{r6['expected']} saved, balance correct")

    # ── Big-O tabell — teoretisk komplexitet ────────────────
    # Visar vad varje operation kostar FÖRE och EFTER optimering
    # O(N) = tiden ökar linjärt med antal rader — 2x rader = 2x tid
    # O(log N) = tiden ökar logaritmiskt — 2x rader = 1 steg till
    # O(K) = beror på antal träffar, inte totalt antal rader
    # O(1) = konstant tid oavsett databasstorlek
    print("""
  Big-O complexity changes:
  ┌──────────────────────────────────┬────────────┬─────────────┐
  │ Operation                        │ Before     │ After       │
  ├──────────────────────────────────┼────────────┼─────────────┤
  │ GET /transactions (all)          │ O(N)       │ O(N)*       │
  ├──────────────────────────────────┼────────────┼─────────────┤
  │ GET /transactions?account_id=X   │ O(N) scan  │ O(K) index  │
  ├──────────────────────────────────┼────────────┼─────────────┤
  │ GET /accounts/{id} (SUM)         │ O(N) scan  │ O(K) index  │
  ├──────────────────────────────────┼────────────┼─────────────┤
  │ GET /transactions/{id}           │ O(N) scan  │ O(1) PK     │
  ├──────────────────────────────────┼────────────┼─────────────┤
  │ POST /transactions               │ O(1)       │ O(1)        │
  └──────────────────────────────────┴────────────┴─────────────┘
  * O(N) unavoidable when returning all rows.
    Mitigated with pagination → O(page_size) per request.
    K = number of transactions for one account.

  Key trade-offs to mention:
  - aiosqlite: non-blocking DB access, prevents event loop starvation
  - WAL mode: allows concurrent reads during writes (vs default journal mode)
  - INDEX on account_id: faster lookups, slight overhead on INSERT
  - Pagination: reduces payload size, adds client-side complexity
  - Cached balance (optional): O(1) reads, but adds write complexity
""")

    # ── Big-O tabell — uppmätta värden ──────────────────────
    # Samma operationer men med FAKTISKA mätvärden från denna körning
    print(f"""
  Big-O complexity (measured):
  ┌──────────────────────────────────┬────────────────┬─────────────┐
  │ Operation                        │ Current        │ Target      │
  ├──────────────────────────────────┼────────────────┼─────────────┤
  │ GET /accounts/{{id}} (SUM)         │ {r3['balance_median']:>8.1f}ms     │ <20ms       │
  │ GET /transactions?account_id=X   │ {r3['filter_median']:>8.1f}ms     │ <100ms      │
  │ /ping under load                 │ {r1['ping_median']:>8.0f}ms     │ <100ms      │
  │ Throughput                       │ {r4['rps']:>8.0f} req/s │ >1000 req/s │
  │ Parallelism ratio                │ {r7['ratio']:>8.1f}x      │ >2.0x       │
  └──────────────────────────────────┴────────────────┴─────────────┘""")
    print('=' * 60)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STARTPUNKT — körs bara vid direkt exekvering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# __name__ == '__main__' → True bara vid: python test-optimizations.py
# Inte vid import från annan fil
if __name__ == '__main__':
    # asyncio.run() = starta Pythons async-motor och kör main()
    # Hela scriptet är asynkront (async/await) för att kunna skicka
    # hundratals HTTP-anrop parallellt
    asyncio.run(main())

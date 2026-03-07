/**
 * App.jsx — Huvudkomponenten i React-appen (all frontend-logik).
 *
 * LAYOUT: Två paneler
 *   Vänster: Formulär för ny transaktion (account_id + amount) + "Show account count"-knapp
 *   Höger:   Sökfält för att filtrera per konto + transaktionslista
 *
 * STATE:
 *   accountId        — input: kontonummer i formuläret
 *   amount           — input: belopp i formuläret
 *   transactions     — lista med transaktioner som visas i höger panel
 *   error            — felmeddelande som visas i UI
 *   searchAccountId  — input: sökfält för att filtrera per konto
 *   accountCount     — antal unika konton (från GET /accounts/count)
 *   accountIds       — lista med konto-ID:n
 *
 * FUNKTIONER:
 *   handleSearch()   — hämtar transaktioner via GET /transactions?account_id=X
 *   validateInput()  — avvisar numeriska account_id och icke-numeriska belopp
 *   handleSubmit()   — POST:ar ny transaktion, hämtar sedan transaktionen + balans
 *
 * VIKTIGA data-* ATTRIBUT (Cypress-testerna letar efter dessa — RÖR DEM INTE):
 *   data-type="account-id"          — input för kontonummer
 *   data-type="amount"              — input för belopp
 *   data-type="transaction-submit"  — submit-knappen
 *   data-type="transaction"         — varje transaktionsrad
 *   data-account-id                 — kontot på en rad
 *   data-amount                     — beloppet på en rad
 *   data-balance                    — balansen (visas bara på senaste transaktionen)
 *
 * BEROENDEN:
 *   index.jsx → importerar App → denna fil → importerar App.css (styling)
 *                                           → fetch() → server.py (backend, port 8000)
 */
// Importerar React-hooks: useState (hantera state), useEffect (sidoeffekter, ej använd just nu)
import { useState, useEffect } from "react";
// Importerar CSS-styling för App-komponenten (layout, formulär, transaktionskort etc.)
import "./App.css";

// Backend-API:ets basadress — alla fetch-anrop går hit
const API_URL = "http://localhost:8000";

// Huvudkomponenten — allt som visas i appen definieras här
function App() {
  // --- STATE (variabler som React "bevakar" — UI uppdateras automatiskt när de ändras) ---

  const [accountId, setAccountId] = useState(""); // Kontonummer från formuläret (text-input)
  const [amount, setAmount] = useState(""); // Belopp från formuläret (text-input)
  const [transactions, setTransactions] = useState([]); // Lista med transaktioner som visas i höger panel
  const [error, setError] = useState(""); // Felmeddelande som visas i röd text
  const [searchAccountId, setSearchAccountId] = useState(""); // Sökvärde för att filtrera transaktioner per konto
  const [accountCount, setAccountCount] = useState(null); // Antal unika konton (visas efter knapptryck)
  const [accountIds, setAccountIds] = useState([]); // Lista med konto-ID:n (visas under räknaren)

  // --- FUNKTION: Sök transaktioner ---
  // Hämtar transaktioner från backend. Om searchAccountId är ifyllt filtreras per konto.
  const handleSearch = async () => {
    try {
      setError(""); // Rensa eventuellt gammalt felmeddelande
      // Bygg query string — om sökfältet är tomt hämtas ALLA transaktioner
      const query = searchAccountId
        ? `?account_id=${encodeURIComponent(searchAccountId)}` // encodeURIComponent skyddar mot specialtecken i URL
        : "";
      const res = await fetch(`${API_URL}/transactions${query}`); // GET-anrop till backend
      const data = await res.json(); // Parsa JSON-svaret till en JS-array
      setTransactions(data); // Uppdatera state → React renderar om listan
    } catch (err) {
      setError("Failed to load transactions"); // Visa fel om nätverksanrop misslyckas
    }
  };

  // --- FUNKTION: Validera input ---
  // Körs innan formuläret skickas. Returnerar true om allt är OK, false om ej.
  const validateInput = () => {
    setError(""); // Rensa gammalt felmeddelande

    // account_id FÅR INTE vara ett rent nummer (Cypress-testet testar detta)
    // isNaN("abc") = true (bra), isNaN("123") = false (dåligt — avvisas)
    if (!isNaN(accountId) && accountId !== "") {
      setError("Invalid account ID");
      return false; // Stoppa formuläret
    }

    // amount MÅSTE vara ett nummer
    const amountNum = parseFloat(amount); // Försök konvertera strängen till tal
    if (isNaN(amountNum)) {
      setError("Invalid amount");
      return false; // Stoppa formuläret
    }

    return true; // Allt OK — formuläret får skickas
  };

  // --- FUNKTION: Skicka ny transaktion ---
  // Körs när användaren klickar "Submit". Gör 3 API-anrop i följd.
  const handleSubmit = async (e) => {
    e.preventDefault(); // Förhindra att sidan laddas om (standard HTML-beteende)

    // Steg 1: Validera — avbryt om ogiltigt
    if (!validateInput()) {
      return;
    }

    try {
      // Steg 2: POST — skapa transaktionen i databasen
      const response = await fetch(`${API_URL}/transactions`, {
        method: "POST", // HTTP-metod
        headers: {
          "Content-Type": "application/json", // Talar om att body är JSON
        },
        body: JSON.stringify({
          // Konvertera JS-objekt till JSON-sträng
          account_id: accountId, // Kontot att boka på
          amount: parseFloat(amount), // Beloppet som tal (inte sträng)
        }),
      });

      // Om servern svarar med fel (t.ex. 400, 500) — kasta ett undantag
      if (!response.ok) {
        throw new Error("Failed to create transaction");
      }

      // Servern returnerar { transaction_id: 123 } — vi behöver ID:t
      const data = await response.json();

      // Steg 3: GET — hämta den nyskapade transaktionens detaljer
      // (servern returnerar hela objektet med account_id, amount etc.)
      const transactionResponse = await fetch(
        `${API_URL}/transactions/${data.transaction_id}`,
      );
      const transactionData = await transactionResponse.json();

      // Steg 4: GET — hämta kontots aktuella balans (SUM av alla belopp)
      const balanceResponse = await fetch(`${API_URL}/accounts/${accountId}`);
      const balanceData = await balanceResponse.json();

      // Steg 5: Lägg till transaktionen FÖRST i listan (senaste överst)
      // Spread-operatorn (...) kopierar alla fält från transactionData
      // och lägger till balance från balansanropet
      setTransactions((prev) => [
        {
          ...transactionData, // transaction_id, account_id, amount
          balance: balanceData.balance, // aktuell balans för kontot
        },
        ...prev, // alla tidigare transaktioner kommer efter
      ]);

      // Steg 6: Töm formuläret efter lyckad submission
      setAccountId("");
      setAmount("");
      setError("");
    } catch (err) {
      setError(err.message); // Visa felmeddelandet i UI
    }
  };

  // --- JSX: Det som renderas i webbläsaren ---
  return (
    // Yttersta wrapper med CSS-klass "App" (centrerar innehåll)
    <div className="App">
      {/* Layout: flexbox med två paneler sida vid sida */}
      <div className="layout">
        {/* === VÄNSTER PANEL: Formulär + kontoräknare === */}
        <div className="left-panel">
          <h2>Submit new transaction</h2>

          {/* Formulär — onSubmit triggar handleSubmit när Enter/Submit */}
          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label>Account ID:</label>
              <input
                type="text"
                value={accountId} // Kontrollerad input — värdet styrs av state
                onChange={(e) => setAccountId(e.target.value)} // Varje knapptryck uppdaterar state
                required // HTML5-validering: fältet måste fyllas i
                data-type="account-id" // ⚠️ CYPRESS-SELEKTOR — rör ej!
              />
            </div>
            <div className="form-group">
              <label>Amount:</label>
              <input
                type="text"
                value={amount} // Kontrollerad input
                onChange={(e) => setAmount(e.target.value)} // Uppdatera belopp-state
                required // Måste fyllas i
                data-type="amount" // ⚠️ CYPRESS-SELEKTOR — rör ej!
              />
            </div>
            {/* Visa felmeddelande i rött om error-state inte är tomt */}
            {error && <div className="error">{error}</div>}
            <button type="submit" data-type="transaction-submit">
              {" "}
              {/* ⚠️ CYPRESS-SELEKTOR */}
              Submit
            </button>
          </form>

          {/* --- Kontoräknare (extra feature, testas ej av Cypress) --- */}
          <div style={{ marginTop: "24px" }}>
            <button
              type="button" // type="button" förhindrar att formuläret submittas
              onClick={async () => {
                try {
                  // Hämta antal unika konton + deras ID:n från backend
                  const res = await fetch(`${API_URL}/accounts/count`);
                  const data = await res.json();
                  setAccountCount(data.count); // Spara antal
                  setAccountIds(data.account_ids); // Spara ID-listan
                } catch (err) {
                  setError("Failed to fetch account count");
                }
              }}
            >
              Show account count
            </button>
            {/* Visa räknaren bara om den hämtats (inte null) */}
            {accountCount !== null && (
              <div>
                <p>
                  The database contains <strong>{accountCount}</strong> unique
                  accounts.
                </p>
                {/* Scrollbar lista med alla konto-ID:n */}
                <ul
                  style={{
                    maxHeight: "200px", // Max höjd — scroll vid overflow
                    overflowY: "auto", // Vertikal scrollbar vid behov
                    textAlign: "left",
                    paddingLeft: "20px",
                  }}
                >
                  {/* Loopa igenom alla konto-ID:n och visa som lista */}
                  {accountIds.map((id) => (
                    <li key={id}>{id}</li> // key={id} krävs av React för effektiv rendering
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* === HÖGER PANEL: Sök + transaktionshistorik === */}
        <div className="right-panel">
          <h2>Transaction history</h2>

          {/* Sökfält — filtrerar transaktioner per konto (extra feature) */}
          <div
            className="form-group"
            style={{ display: "flex", gap: "8px", marginBottom: "16px" }}
          >
            <input
              type="text"
              placeholder="Search by Account ID"
              value={searchAccountId}
              onChange={(e) => setSearchAccountId(e.target.value)}
            />
            <button type="button" onClick={handleSearch}>
              Search
            </button>
          </div>

          {/* Transaktionslista — varje transaktion visas som ett kort */}
          <div className="transactions-list">
            {transactions.map((tx, index) => {
              const isNegative = tx.amount < 0; // Negativt belopp = uttag
              const isLatestTransaction = index === 0; // Första i listan = senaste (visas med balans)
              return (
                <div
                  key={tx.transaction_id} // Unikt ID för React-rendering
                  className="transaction-item"
                  data-type="transaction" // ⚠️ CYPRESS-SELEKTOR — rör ej!
                  data-account-id={tx.account_id} // ⚠️ CYPRESS-SELEKTOR — rör ej!
                  data-amount={tx.amount} // ⚠️ CYPRESS-SELEKTOR — rör ej!
                  data-balance={tx.balance} // ⚠️ CYPRESS-SELEKTOR — rör ej!
                >
                  {/* Villkorlig rendering: uttag eller insättning */}
                  {isNegative ? (
                    // UTTAG — negativt belopp, visa absolutvärde med Math.abs()
                    <div className="withdrawal">
                      <div>Transaction amount (withdrawal)</div>
                      <div>
                        Transferred <code>${Math.abs(tx.amount)}</code> from
                        account <strong>{tx.account_id}</strong>
                      </div>
                    </div>
                  ) : (
                    // INSÄTTNING — positivt belopp
                    <div className="deposit">
                      <div>Transaction amount (deposit)</div>
                      <div>
                        Transferred <code>${tx.amount}</code> to account{" "}
                        <strong>{tx.account_id}</strong>
                      </div>
                    </div>
                  )}
                  {/* Visa balans BARA på senaste transaktionen (index === 0) */}
                  {isLatestTransaction && (
                    <div className="balance-info">
                      The current account balance is <code>${tx.balance}</code>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

// Exportera komponenten så index.jsx kan importera den
export default App;

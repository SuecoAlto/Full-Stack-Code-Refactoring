/**
 * App — Main layout component.
 * Composes TransactionForm, TransactionList, and the account counter.
 * All state and business logic lives in the useTransactions hook.
 */

import { useTransactions } from "./hooks/useTransactions";
import TransactionForm from "./components/TransactionForm";
import TransactionList from "./components/TransactionList";
import "./App.css";

function App() {
  const {
    transactions,
    error,
    accountCount,
    accountIds,
    handleSubmit,
    handleSearch,
    loadAccountCount,
  } = useTransactions();

  return (
    <div className="App">
      <div className="layout">
        <div className="left-panel">
          <TransactionForm onSubmit={handleSubmit} error={error} />

          <div style={{ marginTop: "24px" }}>
            <button type="button" onClick={loadAccountCount}>
              Show account count
            </button>
            {accountCount !== null && (
              <div>
                <p>
                  The database contains <strong>{accountCount}</strong> unique
                  accounts.
                </p>
                <ul
                  style={{
                    maxHeight: "200px",
                    overflowY: "auto",
                    textAlign: "left",
                    paddingLeft: "20px",
                  }}
                >
                  {accountIds.map((id) => (
                    <li key={id}>{id}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>

        <div className="right-panel">
          <TransactionList
            transactions={transactions}
            onSearch={handleSearch}
          />
        </div>
      </div>
    </div>
  );
}

export default App;

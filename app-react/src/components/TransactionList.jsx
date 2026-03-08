/**
 * TransactionList — right-panel component displaying the search
 * bar and the scrollable transaction history.
 */

import { useState } from "react";
import TransactionItem from "./TransactionItem";

/**
 * @param {Object}   props
 * @param {Array}    props.transactions - Array of transaction objects to render.
 * @param {Function} props.onSearch     - Called with the search account ID string.
 */
function TransactionList({ transactions, onSearch }) {
  const [searchAccountId, setSearchAccountId] = useState("");

  return (
    <>
      <h2>Transaction history</h2>
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
        <button type="button" onClick={() => onSearch(searchAccountId)}>
          Search
        </button>
      </div>
      <div className="transactions-list">
        {transactions.map((tx, index) => (
          <TransactionItem
            key={tx.transaction_id}
            transaction={tx}
            isLatest={index === 0}
          />
        ))}
      </div>
    </>
  );
}

export default TransactionList;

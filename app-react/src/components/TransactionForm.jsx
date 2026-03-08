/**
 * TransactionForm — left-panel form for creating new transactions.
 * Manages its own local input state; delegates submission logic
 * to the parent via the onSubmit callback.
 */

import { useState } from "react";

/**
 * @param {Object}   props
 * @param {Function} props.onSubmit - Called with (accountId, amount). Must return a boolean promise.
 * @param {string}   props.error   - Error message to display below the form.
 */
function TransactionForm({ onSubmit, error }) {
  const [accountId, setAccountId] = useState("");
  const [amount, setAmount] = useState("");

  const handleFormSubmit = async (e) => {
    e.preventDefault();
    const success = await onSubmit(accountId, amount);
    if (success) {
      setAccountId("");
      setAmount("");
    }
  };

  return (
    <>
      <h2>Submit new transaction</h2>
      <form onSubmit={handleFormSubmit}>
        <div className="form-group">
          <label>Account ID:</label>
          <input
            type="text"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            required
            data-type="account-id"
          />
        </div>
        <div className="form-group">
          <label>Amount:</label>
          <input
            type="text"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            data-type="amount"
          />
        </div>
        {error && <div className="error">{error}</div>}
        <button type="submit" data-type="transaction-submit">
          Submit
        </button>
      </form>
    </>
  );
}

export default TransactionForm;

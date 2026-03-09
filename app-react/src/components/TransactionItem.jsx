/**
 * TransactionItem — a single row in the transaction history.
 * Renders deposit (green) or withdrawal (red) styling based on
 * the sign of the amount.
 */

/**
 * @param {Object}  props
 * @param {Object}  props.transaction - Transaction object with account_id, amount, balance.
 * @param {boolean} props.isLatest    - True for the most recently added transaction.
 */
function TransactionItem({ transaction: tx, isLatest }) {
  const isNegative = tx.amount < 0;

  return (
    <div
      className="transaction-item"
      data-type="transaction"
      data-account-id={tx.account_id}
      data-amount={tx.amount}
      data-balance={tx.balance}
    >
      {isNegative ? (
        <div className="withdrawal">
          <div>Transaction amount (withdrawal)</div>
          <div>
            Withdrew <code>-${Math.abs(tx.amount)}</code> from account{" "}
            <strong>{tx.account_id}</strong>
          </div>
        </div>
      ) : (
        <div className="deposit">
          <div>Transaction amount (deposit)</div>
          <div>
            Transferred <code>${tx.amount}</code> to account{" "}
            <strong>{tx.account_id}</strong>
          </div>
        </div>
      )}
      {isLatest && tx.balance != null && (
        <div className="balance-info">
          The current account balance is <code>${tx.balance}</code>
        </div>
      )}
    </div>
  );
}

export default TransactionItem;

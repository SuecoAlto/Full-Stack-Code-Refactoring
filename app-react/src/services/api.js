/**
 * API service layer — all network requests to the backend.
 * Components and hooks never call fetch() directly; they use
 * these functions instead.  This makes the network boundary
 * explicit and easy to mock in tests.
 */

const API_URL = "http://localhost:8000";

/**
 * Create a new transaction.
 * @param {string} accountId - The account to transact on.
 * @param {number} amount - The transaction amount (positive = deposit, negative = withdrawal).
 * @returns {Promise<Object>} Response containing the generated transaction_id.
 */
export async function createTransaction(accountId, amount) {
	const response = await fetch(`${API_URL}/transactions`, {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ account_id: accountId, amount }),
	});

	if (!response.ok) {
		const body = await response.json().catch(() => ({}));
		throw new Error(body.error || "Failed to create transaction");
	}

	return response.json();
}

/**
 * Fetch a single transaction by its ID.
 * @param {string} transactionId
 * @returns {Promise<Object>} Transaction details (transaction_id, account_id, amount).
 */
export async function fetchTransaction(transactionId) {
	const response = await fetch(`${API_URL}/transactions/${transactionId}`);

	if (!response.ok) {
		throw new Error("Failed to fetch transaction");
	}

	return response.json();
}

/**
 * Fetch account data (balance) by account ID.
 * @param {string} accountId
 * @returns {Promise<Object>} Account object with account_id and balance.
 */
export async function fetchAccount(accountId) {
	const response = await fetch(`${API_URL}/accounts/${accountId}`);

	if (!response.ok) {
		throw new Error("Failed to fetch account");
	}

	return response.json();
}

/**
 * Fetch all transactions, optionally filtered by account ID.
 * @param {string} [accountId] - Optional filter.
 * @returns {Promise<Array>} Array of transaction objects.
 */
export async function fetchTransactions(accountId) {
	const query = accountId
		? `?account_id=${encodeURIComponent(accountId)}`
		: "";
	const response = await fetch(`${API_URL}/transactions${query}`);

	if (!response.ok) {
		throw new Error("Failed to load transactions");
	}

	return response.json();
}

/**
 * Fetch the count of unique accounts and their IDs.
 * @returns {Promise<Object>} Object with count and account_ids array.
 */
export async function fetchAccountCount() {
	const response = await fetch(`${API_URL}/accounts/count`);

	if (!response.ok) {
		throw new Error("Failed to fetch account count");
	}

	return response.json();
}
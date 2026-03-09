/**
 * Custom hook — encapsulates all transaction-related state and
 * side-effect logic.  Components consume this hook to stay
 * focused purely on rendering.
 */

import { useState } from "react";
import {
	createTransaction,
	fetchTransaction,
	fetchAccount,
	fetchTransactions,
	fetchAccountCount,
} from "../services/api";

/**
 * Manage transaction list, errors, and account data.
 * @returns {Object} State values and handler functions.
 */
export function useTransactions() {
	const [transactions, setTransactions] = useState([]);
	const [error, setError] = useState("");
	const [accountCount, setAccountCount] = useState(null);
	const [accountIds, setAccountIds] = useState([]);

	/**
	 * Validate form input before submission.
	 * @param {string} accountId - Raw input value.
	 * @param {string} amount - Raw input value.
	 * @returns {boolean} True if valid.
	 */
	const validateInput = (accountId, amount) => {
		setError("");

		// account_id must not be a pure number
		if (!isNaN(accountId) && accountId !== "") {
			setError("Invalid account ID");
			return false;
		}

		if (isNaN(Number(amount))) {
			setError("Invalid amount");
			return false;
		}

		return true;
	};

	/**
	 * Submit a new transaction: validate → POST → GET details → GET balance.
	 * @param {string} accountId
	 * @param {string} amount - Raw string from the input field.
	 * @returns {Promise<boolean>} True if successful (form should clear).
	 */
	const handleSubmit = async (accountId, amount) => {
		if (!validateInput(accountId, amount)) {
			return false;
		}

		try {
			const data = await createTransaction(accountId, Number(amount));
			const transactionData = await fetchTransaction(data.transaction_id);
			const balanceData = await fetchAccount(accountId);

			setTransactions((prev) => [
				{ ...transactionData, balance: balanceData.balance },
				...prev,
			]);
			setError("");
			return true;
		} catch (err) {
			setError(err.message);
			return false;
		}
	};

	/**
	 * Search/filter transactions by account ID.
	 * @param {string} [searchAccountId]
	 */
	const handleSearch = async (searchAccountId) => {
		try {
			setError("");
			const data = await fetchTransactions(searchAccountId);
			setTransactions(data);
		} catch (err) {
			setError("Failed to load transactions");
		}
	};

	/**
	 * Load the unique account count from the backend.
	 */
	const loadAccountCount = async () => {
		try {
			const data = await fetchAccountCount();
			setAccountCount(data.count);
			setAccountIds(data.account_ids);
		} catch (err) {
			setError("Failed to fetch account count");
		}
	};

	return {
		transactions,
		error,
		accountCount,
		accountIds,
		handleSubmit,
		handleSearch,
		loadAccountCount,
	};
}

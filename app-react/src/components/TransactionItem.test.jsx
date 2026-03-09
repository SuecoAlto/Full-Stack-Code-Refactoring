import { render, screen } from "@testing-library/react";
import TransactionItem from "./TransactionItem";

describe("TransactionItem", () => {
  it("renders a deposit with the 'deposit' CSS class for positive amounts", () => {
    const tx = { account_id: "acc-1", amount: 100, balance: 100 };
    render(<TransactionItem transaction={tx} isLatest={false} />);

    const amountElement = screen.getByText("$100");
    expect(amountElement).toBeInTheDocument();
    expect(amountElement.closest(".deposit")).toBeInTheDocument();
    expect(amountElement.closest(".withdrawal")).not.toBeInTheDocument();
  });

  it("renders a withdrawal with the 'withdrawal' CSS class for negative amounts", () => {
    const tx = { account_id: "acc-2", amount: -50, balance: 50 };
    render(<TransactionItem transaction={tx} isLatest={false} />);

    const amountElement = screen.getByText("-$50");
    expect(amountElement).toBeInTheDocument();
    expect(amountElement.closest(".withdrawal")).toBeInTheDocument();
    expect(amountElement.closest(".deposit")).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TransactionForm from "./TransactionForm";

describe("TransactionForm", () => {
  test("renders error message when error prop is set", () => {
    render(<TransactionForm onSubmit={vi.fn()} error="Invalid amount" />);

    const errorEl = screen.getByText("Invalid amount");
    expect(errorEl).toBeInTheDocument();
    expect(errorEl).toHaveClass("error");
  });

  test("preserves input values when onSubmit returns false", async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.fn().mockResolvedValue(false);

    render(<TransactionForm onSubmit={mockSubmit} error="" />);

    const accountInput = screen.getByLabelText("Account ID:");
    const amountInput = screen.getByLabelText("Amount:");

    await user.type(accountInput, "abc123");
    await user.type(amountInput, "500");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(mockSubmit).toHaveBeenCalledWith("abc123", "500");
    expect(accountInput).toHaveValue("abc123");
    expect(amountInput).toHaveValue("500");
  });

  test("clears input values when onSubmit returns true", async () => {
    const user = userEvent.setup();
    const mockSubmit = vi.fn().mockResolvedValue(true);

    render(<TransactionForm onSubmit={mockSubmit} error="" />);

    const accountInput = screen.getByLabelText("Account ID:");
    const amountInput = screen.getByLabelText("Amount:");

    await user.type(accountInput, "abc123");
    await user.type(amountInput, "500");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(mockSubmit).toHaveBeenCalledWith("abc123", "500");
    expect(accountInput).toHaveValue("");
    expect(amountInput).toHaveValue("");
  });
});

import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders main layout without crashing", () => {
  render(<App />);
  expect(screen.getByText("Submit new transaction")).toBeInTheDocument();
  expect(screen.getByText("Transaction history")).toBeInTheDocument();
});

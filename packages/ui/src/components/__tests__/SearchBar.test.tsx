import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SearchBar } from "../SearchBar";

describe("SearchBar", () => {
  it("renders input with placeholder", () => {
    render(<SearchBar value="" onChange={() => undefined} placeholder="Find disease…" />);
    expect(screen.getByPlaceholderText("Find disease…")).toBeInTheDocument();
  });

  it("shows clear button when value is non-empty", () => {
    render(<SearchBar value="PKU" onChange={() => undefined} />);
    expect(screen.getByRole("button", { name: "Clear search" })).toBeInTheDocument();
  });

  it("hides clear button when value is empty", () => {
    render(<SearchBar value="" onChange={() => undefined} />);
    expect(screen.queryByRole("button", { name: "Clear search" })).not.toBeInTheDocument();
  });

  it("calls onChange with empty string when clear is clicked", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<SearchBar value="PKU" onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("calls onChange when typing", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<SearchBar value="" onChange={onChange} />);
    await user.type(screen.getByRole("searchbox"), "P");
    expect(onChange).toHaveBeenCalled();
    rerender(<SearchBar value="P" onChange={onChange} />);
  });
});

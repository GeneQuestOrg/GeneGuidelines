import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Button } from "../Button";

describe("Button", () => {
  it("renders with default variant", () => {
    render(<Button>Click me</Button>);
    const btn = screen.getByRole("button", { name: "Click me" });
    expect(btn).toHaveClass("btn");
    expect(btn).not.toHaveClass("btn--primary");
    expect(btn).not.toHaveClass("btn--ghost");
  });

  it("renders primary variant", () => {
    render(<Button variant="primary">Save</Button>);
    expect(screen.getByRole("button", { name: "Save" })).toHaveClass("btn--primary");
  });

  it("renders ghost variant", () => {
    render(<Button variant="ghost">Cancel</Button>);
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveClass("btn--ghost");
  });

  it("renders sm size", () => {
    render(<Button size="sm">Small</Button>);
    expect(screen.getByRole("button", { name: "Small" })).toHaveClass("btn--sm");
  });

  it("renders lg size", () => {
    render(<Button size="lg">Large</Button>);
    expect(screen.getByRole("button", { name: "Large" })).toHaveClass("btn--lg");
  });

  it("forwards disabled prop", () => {
    render(<Button disabled>Disabled</Button>);
    expect(screen.getByRole("button", { name: "Disabled" })).toBeDisabled();
  });

  it("sanitizes unsafe href when rendered as anchor", () => {
    render(
      <Button as="a" href="javascript:alert(1)">
        Link
      </Button>,
    );
    const link = screen.getByRole("link", { name: "Link" });
    expect(link).toHaveAttribute("href", "#");
  });

  it("keeps safe hash href when rendered as anchor", () => {
    render(
      <Button as="a" href="#/diseases">
        Diseases
      </Button>,
    );
    expect(screen.getByRole("link", { name: "Diseases" })).toHaveAttribute("href", "#/diseases");
  });
});

import { render, screen } from "@testing-library/react";
import { SeverityBadge, DemoBadge, ModeBadge } from "./Badge";

describe("SeverityBadge", () => {
  it.each(["LOW", "MEDIUM", "HIGH", "CRITICAL"] as const)("renders the %s label", (severity) => {
    render(<SeverityBadge severity={severity} />);
    expect(screen.getByText(severity)).toBeInTheDocument();
  });
});

describe("DemoBadge", () => {
  it("renders a DEMO label with an explanatory title", () => {
    render(<DemoBadge />);
    const badge = screen.getByText("DEMO");
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute("title", expect.stringContaining("Simulated"));
  });
});

describe("ModeBadge", () => {
  it("renders DEMO badge for demo mode", () => {
    render(<ModeBadge mode="DEMO" />);
    expect(screen.getByText("DEMO")).toBeInTheDocument();
  });

  it("renders REAL badge for real mode", () => {
    render(<ModeBadge mode="REAL" />);
    expect(screen.getByText("REAL")).toBeInTheDocument();
  });
});

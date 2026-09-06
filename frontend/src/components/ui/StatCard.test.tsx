import { render, screen } from "@testing-library/react";
import { Camera } from "lucide-react";
import { StatCard } from "./StatCard";

describe("StatCard", () => {
  it("renders the label and value", () => {
    render(<StatCard label="Total Cameras" value={5} icon={Camera} />);
    expect(screen.getByText("Total Cameras")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("renders an optional hint", () => {
    render(<StatCard label="Active Alerts" value={2} icon={Camera} hint="Since last hour" />);
    expect(screen.getByText("Since last hour")).toBeInTheDocument();
  });
});

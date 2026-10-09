import { describe, expect, it } from "vitest";
import { change, money, monthLabel } from "./format";
import { toQuery } from "./api";

describe("format", () => {
  it("formats money", () => {
    expect(money(1234.5)).toBe("$1,234.50");
    expect(money(-3)).toBe("-$3.00");
  });
  it("labels months without timezone drift", () => {
    expect(monthLabel("2026-01")).toBe("Jan 2026");
    expect(monthLabel("2026-12", true)).toBe("Dec");
  });
  it("computes change", () => {
    expect(change(110, 100)).toBeCloseTo(0.1);
    expect(change(5, 0)).toBeNull();
  });
});

describe("toQuery", () => {
  it("skips empty values and repeats arrays", () => {
    expect(toQuery({ a: "x", b: undefined, c: ["1", "2"], d: "" })).toBe("?a=x&c=1&c=2");
    expect(toQuery({})).toBe("");
  });
});

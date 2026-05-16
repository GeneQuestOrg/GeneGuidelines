import { useState } from "react";
import {
  Button,
  Badge,
  Status,
  Section,
  SearchBar,
  AppHeader,
  AuthModal,
} from "@gene-guidelines/ui";
import type { StatusValue } from "@gene-guidelines/ui";

const STATUS_VALUES: StatusValue[] = [
  "pending",
  "under-review",
  "verified",
  "consensus",
  "superseded",
  "rejected",
  "live",
];

export default function DevComponents() {
  const [search, setSearch] = useState("");
  const [showAuth, setShowAuth] = useState(false);

  return (
    <div style={{ padding: "32px 24px", maxWidth: "900px", margin: "0 auto" }}>
      <h1 style={{ fontFamily: "var(--font-serif)", fontWeight: 400, fontSize: "var(--fs-3xl)", marginBottom: "8px" }}>
        Dev Components
      </h1>
      <p style={{ color: "var(--ink-3)", marginBottom: "48px" }}>
        Visual check — Phase 1 design system
      </p>

      <Section title="AppHeader" divider>
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--r-md)", overflow: "hidden", marginBottom: "12px" }}>
          <AppHeader variant="public" />
        </div>
        <div style={{ border: "1px solid var(--line)", borderRadius: "var(--r-md)", overflow: "hidden" }}>
          <AppHeader variant="admin" />
        </div>
      </Section>

      <Section title="Button" count={3} divider>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
          <Button>Default</Button>
          <Button variant="primary">Primary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button size="sm">Small</Button>
          <Button size="lg">Large</Button>
          <Button disabled>Disabled</Button>
          <Button as="a" href="#" variant="primary">Link Button</Button>
        </div>
      </Section>

      <Section title="Badge" divider>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          <Badge>Default</Badge>
          <Badge variant="ok">Verified</Badge>
        </div>
      </Section>

      <Section title="Status" count={STATUS_VALUES.length} divider>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", marginBottom: "12px" }}>
          {STATUS_VALUES.map((s) => (
            <Status key={s} status={s} />
          ))}
        </div>
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {STATUS_VALUES.map((s) => (
            <Status key={s} status={s} compact />
          ))}
        </div>
      </Section>

      <Section title="SearchBar" divider>
        <SearchBar
          value={search}
          onChange={setSearch}
          placeholder="Search diseases…"
        />
      </Section>

      <Section title="AuthModal" divider>
        <Button variant="primary" onClick={() => setShowAuth(true)}>
          Open Auth Modal
        </Button>
        {showAuth && (
          <AuthModal
            onClose={() => setShowAuth(false)}
            onSuccess={(acc) => { console.info("Signed in:", acc); }}
          />
        )}
      </Section>
    </div>
  );
}

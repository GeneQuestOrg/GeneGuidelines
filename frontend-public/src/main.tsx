import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@gene-guidelines/ui/styles/tokens.css";
import "@gene-guidelines/ui/styles/base.css";
import "./index.css";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

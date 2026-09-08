import React from "react";
import ReactDOM from "react-dom/client";

// Self-hosted variable fonts. Geist for the interface, Geist Mono for every
// number: this product is read by comparing figures down a column, and tabular
// mono is what keeps them aligned while they tick.
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/components.css";
import "./styles/map.css";

import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { initTheme } from "./lib/theme";

initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>
);

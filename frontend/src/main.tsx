import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

// Sometype Mono — loaded via @fontsource so Vite bundles + hashes the woff2.
// Reserved for the FlowPanel SSE event log only (the one place mono is
// structurally functional). General Sans is self-hosted in index.css from
// /public/fonts/general-sans/.
import "@fontsource/sometype-mono/400.css";
import "@fontsource/sometype-mono/500.css";

import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

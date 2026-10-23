import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Producer } from "./Producer";
import "@fontsource/barlow/latin-400.css";
import "@fontsource/barlow/latin-500.css";
import "@fontsource/barlow/latin-600.css";
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/barlow-condensed/latin-700.css";
import "@fontsource/caveat/latin-700.css";
import "./styles.css";

// `/producer` (Cloudflare Access protects it once deployed) or `?page=producer` in local previews.
const isProducer = location.pathname.startsWith("/producer") || new URLSearchParams(location.search).get("page") === "producer";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isProducer ? <Producer /> : <App />}
  </StrictMode>,
);

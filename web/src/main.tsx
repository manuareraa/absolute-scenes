import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { Producer } from "./Producer";
import "./styles.css";

// `/producer` (Cloudflare Access protects it once deployed) or `?page=producer` in local previews.
const isProducer = location.pathname.startsWith("/producer") || new URLSearchParams(location.search).get("page") === "producer";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {isProducer ? <Producer /> : <App />}
  </StrictMode>,
);

import { useEffect, useState } from "react";

// M0 placeholder. Stream A replaces this with the 3D pitch and players.
export function App() {
  const [health, setHealth] = useState("checking");
  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? "edge ok" : `edge ${r.status}`))
      .catch(() => "edge offline")
      .then(setHealth);
  }, []);
  return (
    <main style={{ fontFamily: "system-ui", padding: 24 }}>
      <h1>ChalkTalk</h1>
      <p>Every stroke lands on the word that names it.</p>
      <p>
        <small>{health}</small>
      </p>
    </main>
  );
}

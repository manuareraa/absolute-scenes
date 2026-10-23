// The ChalkTalk mark: a speech bubble with a chalk run drawn inside it (talk + telestration).
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <path
        d="M14 12h36a6 6 0 0 1 6 6v22a6 6 0 0 1-6 6H30l-10 9v-9h-6a6 6 0 0 1-6-6V18a6 6 0 0 1 6-6z"
        fill="none"
        stroke="var(--chalk)"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <circle cx="21" cy="35" r="4" fill="none" stroke="var(--chalk)" strokeWidth="3.5" />
      <path d="M25 32c6-9 14-12 22-12" fill="none" stroke="var(--signal)" strokeWidth="4" strokeLinecap="round" />
      <path d="M41 15l7 5-6 6" fill="none" stroke="var(--signal)" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ size = 28, onClick, title }: { size?: number; onClick?(): void; title?: string }) {
  const inner = (
    <>
      <LogoMark size={size} />
      <span className="wordmark">
        Chalk<b>Talk</b>
      </span>
    </>
  );
  return onClick ? (
    <button className="logo" onClick={onClick} title={title} aria-label={title}>
      {inner}
    </button>
  ) : (
    <span className="logo">{inner}</span>
  );
}

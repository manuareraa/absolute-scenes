// Shared-secret check for the crew and producer POSTs. Compares SHA-256 digests so the
// comparison is constant-time and length-independent.
export const SECRET_HEADER = "x-chalktalk-secret";

export async function checkSecret(request: Request, secret: string | undefined): Promise<boolean> {
  const given = request.headers.get(SECRET_HEADER);
  if (!secret || !given) return false;
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(given)),
    crypto.subtle.digest("SHA-256", enc.encode(secret)),
  ]);
  const x = new Uint8Array(a);
  const y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

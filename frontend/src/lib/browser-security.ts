export function browserContentSecurityPolicy(nonce?: string): string {
  // Only server-generated random hex values may become a CSP nonce source.
  const validNonce = nonce && /^[a-f0-9]{64}$/.test(nonce) ? nonce : undefined;
  const scriptSources = validNonce
    ? `'self' 'nonce-${validNonce}' 'strict-dynamic'`
    : "'self'";
  // React and Radix use dynamic style attributes for positioning and charts.
  // This style-only exception does not authorize inline JavaScript.
  const styleSources = validNonce ? `'self' 'nonce-${validNonce}'` : "'self'";
  return "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; " +
    `form-action 'self'; script-src ${scriptSources}; script-src-attr 'none'; ` +
    `style-src ${styleSources}; style-src-elem ${styleSources}; style-src-attr 'unsafe-inline'; ` +
    "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; " +
    "frame-src 'none'; worker-src 'self'; manifest-src 'self'; upgrade-insecure-requests";
}

/**
 * Validate a post-sign-in redirect target taken from the URL.
 *
 * `returnUrl` arrives in the query string, so anyone can craft a sign-in link
 * that sends the user somewhere else after they authenticate (an open
 * redirect). Only same-site paths are allowed. Each rule closes a known escape:
 *
 * - must start with a single "/": rejects absolute URLs and schemes
 *   ("https://evil.example", "javascript:...")
 * - must not start with "//": protocol-relative URLs go off-site
 * - no backslashes: browsers treat "\" like "/", so "/\evil.example" is
 *   protocol-relative too
 * - no control characters or whitespace: browsers strip tabs/newlines, which
 *   can turn "/\t/evil.example" into "//evil.example"
 *
 * As a final check the path is resolved against the current origin and must
 * stay on it.
 */
function hasUnsafeChar(s: string): boolean {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    // Backslash, space, ASCII control characters, DEL.
    if (c === 0x5c || c === 0x20 || c <= 0x1f || c === 0x7f) return true;
  }
  // Any other Unicode whitespace (e.g. U+00A0, U+2028).
  return /\s/.test(s);
}

export function safeReturnPath(raw: string | null | undefined, fallback: string): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//')) return fallback;
  if (hasUnsafeChar(raw)) return fallback;

  try {
    const resolved = new URL(raw, window.location.origin);
    if (resolved.origin !== window.location.origin) return fallback;
    return resolved.pathname + resolved.search + resolved.hash;
  } catch {
    return fallback;
  }
}

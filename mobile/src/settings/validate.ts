export type UrlCheck =
  | { ok: true; url: string; secure: boolean; privateNetwork: boolean }
  | { ok: false; reason: 'empty' | 'invalid' | 'scheme' | 'https_required' };

const URL_PATTERN = /^(https?):\/\/(\[[0-9a-f:]+\]|[^\s/:?#@]+)(?::(\d{1,5}))?(\/[^\s?#]*)?$/i;

/** Private / local-only hosts where plain http is acceptable (LAN, loopback, emulator alias, Tailscale CGNAT). */
export function isPrivateHost(host: string): boolean {
  const h = host.toLowerCase();
  if (h === 'localhost' || h === '[::1]' || h.endsWith('.local')) return true;
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(h);
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  if ([m[1], m[2], m[3], m[4]].some((p) => Number(p) > 255)) return false;
  return (
    a === 10 ||
    a === 127 ||
    (a === 192 && b === 168) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 100 && b >= 64 && b <= 127)
  );
}

/**
 * Normalise what the user typed into a base URL (no trailing slash, no /v1 suffix). Plain http is only accepted
 * for private hosts; anything on the public internet must use https, because frames and the API key travel in it.
 */
export function normalizeRemoteUrl(input: string): UrlCheck {
  const trimmed = input.trim();
  if (!trimmed) return { ok: false, reason: 'empty' };
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(trimmed) && !/^https?:\/\//i.test(trimmed)) {
    return { ok: false, reason: 'scheme' };
  }
  const match = URL_PATTERN.exec(trimmed);
  if (!match) return { ok: false, reason: 'invalid' };
  const scheme = match[1].toLowerCase();
  const host = match[2];
  const port = match[3];
  if (port !== undefined && Number(port) > 65535) return { ok: false, reason: 'invalid' };
  let path = (match[4] ?? '').replace(/\/+$/, '');
  path = path.replace(/\/v1(\/chat\/completions|\/models)?$/i, '');
  const privateNetwork = isPrivateHost(host);
  if (scheme === 'http' && !privateNetwork) return { ok: false, reason: 'https_required' };
  const url = `${scheme}://${host}${port ? `:${port}` : ''}${path}`;
  return { ok: true, url, secure: scheme === 'https', privateNetwork };
}

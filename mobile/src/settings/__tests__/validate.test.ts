import { isPrivateHost, normalizeRemoteUrl } from '../validate';

describe('normalizeRemoteUrl', () => {
  it('accepts https on the public internet and strips trailing slashes', () => {
    expect(normalizeRemoteUrl(' https://gpu.example.com/ ')).toEqual({
      ok: true,
      url: 'https://gpu.example.com',
      secure: true,
      privateNetwork: false,
    });
  });

  it.each([
    ['http://192.168.1.20:8080', 'http://192.168.1.20:8080'],
    ['http://10.0.2.2:18937', 'http://10.0.2.2:18937'],
    ['http://localhost:8080/', 'http://localhost:8080'],
    ['http://myserver.local:8080', 'http://myserver.local:8080'],
    ['http://100.101.102.103:8080', 'http://100.101.102.103:8080'],
    ['http://172.20.0.5', 'http://172.20.0.5'],
  ])('allows plain http only for private hosts: %s', (input, url) => {
    const check = normalizeRemoteUrl(input);
    expect(check).toMatchObject({ ok: true, url, secure: false, privateNetwork: true });
  });

  it.each(['http://example.com', 'http://172.32.0.1', 'http://8.8.8.8:8080', 'http://100.128.0.1'])(
    'refuses plain http to a public host: %s',
    (input) => {
      expect(normalizeRemoteUrl(input)).toEqual({ ok: false, reason: 'https_required' });
    },
  );

  it('strips an OpenAI-style path the user may have pasted', () => {
    expect(normalizeRemoteUrl('https://host.example/v1/chat/completions')).toMatchObject({ url: 'https://host.example' });
    expect(normalizeRemoteUrl('https://host.example/v1')).toMatchObject({ url: 'https://host.example' });
    expect(normalizeRemoteUrl('https://host.example/gateway/v1/')).toMatchObject({ url: 'https://host.example/gateway' });
  });

  it.each([
    ['', 'empty'],
    ['   ', 'empty'],
    ['ftp://host', 'scheme'],
    ['file:///etc/passwd', 'scheme'],
    ['javascript://x', 'scheme'],
    ['not a url', 'invalid'],
    ['https://', 'invalid'],
    ['https://host:70000', 'invalid'],
    ['https://user:pass@host', 'invalid'],
    ['host.example.com', 'invalid'],
  ])('rejects %j as %s', (input, reason) => {
    expect(normalizeRemoteUrl(input)).toEqual({ ok: false, reason });
  });
});

describe('isPrivateHost', () => {
  it('knows the private ranges and nothing else', () => {
    for (const host of ['localhost', '127.0.0.1', '10.1.2.3', '192.168.0.9', '172.16.0.1', '172.31.255.255', '100.64.0.1', 'a.local']) {
      expect(isPrivateHost(host)).toBe(true);
    }
    for (const host of ['172.15.0.1', '172.32.0.1', '100.63.0.1', '100.128.0.1', '192.169.0.1', '11.0.0.1', '300.1.1.1', 'example.com']) {
      expect(isPrivateHost(host)).toBe(false);
    }
  });
});

import {
  createSettingsStore,
  DEFAULT_SETTINGS,
  remoteReadiness,
  sanitizeSettings,
  type KeyValueStore,
  type SecretStore,
  type Settings,
} from '../store';

function memoryStores() {
  const kv: Record<string, string> = {};
  const secrets: Record<string, string> = {};
  const kvStore: KeyValueStore = {
    getItem: async (key) => kv[key] ?? null,
    setItem: async (key, value) => {
      kv[key] = value;
    },
  };
  const secretStore: SecretStore = {
    get: async (key) => secrets[key] ?? null,
    set: async (key, value) => {
      secrets[key] = value;
    },
    remove: async (key) => {
      delete secrets[key];
    },
  };
  return { kv, secrets, store: createSettingsStore(kvStore, secretStore) };
}

describe('sanitizeSettings', () => {
  it('returns defaults for garbage and drops unknown keys', () => {
    expect(sanitizeSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(sanitizeSettings('x')).toEqual(DEFAULT_SETTINGS);
    expect(sanitizeSettings({ mode: 'cloud', language: 'fr', speakResults: 'yes', surprise: 1 })).toEqual(DEFAULT_SETTINGS);
  });

  it('keeps valid values and defaults to local, never to remote', () => {
    const s = sanitizeSettings({ mode: 'remote', language: 'en', speakResults: false, remoteUrl: ' https://a.example ', remoteConsent: true });
    expect(s).toMatchObject({ mode: 'remote', language: 'en', speakResults: false, remoteUrl: 'https://a.example', remoteConsent: true });
    expect(sanitizeSettings({}).mode).toBe('local');
    expect(sanitizeSettings({ remoteConsent: 'true' }).remoteConsent).toBe(false);
  });

  it('bounds string lengths and falls back to the default model name', () => {
    expect(sanitizeSettings({ remoteUrl: 'a'.repeat(1000) }).remoteUrl.length).toBe(300);
    expect(sanitizeSettings({ remoteModel: '   ' }).remoteModel).toBe('minicpm-v4.6');
  });
});

describe('remoteReadiness', () => {
  const base: Settings = { ...DEFAULT_SETTINGS, mode: 'remote', remoteUrl: 'https://gpu.example.com/', remoteConsent: true };

  it('is ready only with a good URL and consent', () => {
    expect(remoteReadiness(base)).toEqual({ ok: true, baseUrl: 'https://gpu.example.com' });
    expect(remoteReadiness({ ...base, remoteConsent: false })).toEqual({ ok: false, reason: 'no_consent' });
    expect(remoteReadiness({ ...base, remoteUrl: '' })).toEqual({ ok: false, reason: 'no_url' });
    expect(remoteReadiness({ ...base, remoteUrl: 'http://example.com' })).toEqual({ ok: false, reason: 'https_required' });
    expect(remoteReadiness({ ...base, remoteUrl: 'ftp://x' })).toEqual({ ok: false, reason: 'bad_url' });
  });

  it('lets a private-network server use plain http', () => {
    expect(remoteReadiness({ ...base, remoteUrl: 'http://192.168.1.5:8080' })).toEqual({ ok: true, baseUrl: 'http://192.168.1.5:8080' });
  });
});

describe('createSettingsStore', () => {
  it('round-trips settings and returns defaults when nothing is stored or the data is corrupt', async () => {
    const { store, kv } = memoryStores();
    expect(await store.load()).toEqual(DEFAULT_SETTINGS);
    const saved = await store.save({ ...DEFAULT_SETTINGS, language: 'en', mode: 'remote' });
    expect(await store.load()).toEqual(saved);
    kv['visualintel.settings.v1'] = '{not json';
    expect(await store.load()).toEqual(DEFAULT_SETTINGS);
  });

  it('keeps the API key out of the settings blob', async () => {
    const { store, kv, secrets } = memoryStores();
    await store.setApiKey('  sk-secret  ');
    await store.save({ ...DEFAULT_SETTINGS, remoteUrl: 'https://a.example' });
    expect(await store.getApiKey()).toBe('sk-secret');
    expect(Object.values(kv).join('')).not.toContain('sk-secret');
    expect(Object.keys(secrets)).toHaveLength(1);
    await store.setApiKey('   ');
    expect(await store.getApiKey()).toBe('');
    expect(Object.keys(secrets)).toHaveLength(0);
  });
});

import type { Language, ProviderId } from '../core/types';
import { normalizeRemoteUrl } from './validate';

export interface Settings {
  mode: ProviderId;
  /** Drives the interface, the model's answer language, speech output and speech recognition. */
  language: Language;
  speakResults: boolean;
  /** As typed; normalised with `normalizeRemoteUrl` when used. */
  remoteUrl: string;
  remoteModel: string;
  /** The user explicitly agreed that pictures are sent to the configured server. */
  remoteConsent: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  mode: 'local',
  language: 'zh',
  speakResults: true,
  remoteUrl: '',
  remoteModel: 'minicpm-v4.6',
  remoteConsent: false,
};

/** Tolerant reader: wrong types or unknown values fall back to the defaults, unknown keys are dropped. */
export function sanitizeSettings(raw: unknown): Settings {
  const r = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>;
  return {
    mode: r.mode === 'remote' ? 'remote' : 'local',
    language: r.language === 'en' ? 'en' : 'zh',
    speakResults: typeof r.speakResults === 'boolean' ? r.speakResults : DEFAULT_SETTINGS.speakResults,
    remoteUrl: typeof r.remoteUrl === 'string' ? r.remoteUrl.trim().slice(0, 300) : '',
    remoteModel:
      typeof r.remoteModel === 'string' && r.remoteModel.trim() ? r.remoteModel.trim().slice(0, 100) : DEFAULT_SETTINGS.remoteModel,
    remoteConsent: r.remoteConsent === true,
  };
}

export type RemoteReadiness = { ok: true; baseUrl: string } | { ok: false; reason: 'no_url' | 'bad_url' | 'https_required' | 'no_consent' };

/** Remote mode may only be used with a valid URL AND the user's explicit consent. */
export function remoteReadiness(settings: Settings): RemoteReadiness {
  const check = normalizeRemoteUrl(settings.remoteUrl);
  if (!check.ok) {
    if (check.reason === 'empty') return { ok: false, reason: 'no_url' };
    if (check.reason === 'https_required') return { ok: false, reason: 'https_required' };
    return { ok: false, reason: 'bad_url' };
  }
  if (!settings.remoteConsent) return { ok: false, reason: 'no_consent' };
  return { ok: true, baseUrl: check.url };
}

export interface KeyValueStore {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
}
export interface SecretStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
}

const SETTINGS_KEY = 'visualintel.settings.v1';
const API_KEY = 'visualintel.remote.apiKey';

export function createSettingsStore(kv: KeyValueStore, secrets: SecretStore) {
  return {
    async load(): Promise<Settings> {
      try {
        const text = await kv.getItem(SETTINGS_KEY);
        return sanitizeSettings(text ? JSON.parse(text) : null);
      } catch {
        return { ...DEFAULT_SETTINGS };
      }
    },
    async save(settings: Settings): Promise<Settings> {
      const clean = sanitizeSettings(settings);
      await kv.setItem(SETTINGS_KEY, JSON.stringify(clean));
      return clean;
    },
    async getApiKey(): Promise<string> {
      try {
        return (await secrets.get(API_KEY)) ?? '';
      } catch {
        return '';
      }
    },
    async setApiKey(value: string): Promise<void> {
      const trimmed = value.trim();
      if (trimmed) await secrets.set(API_KEY, trimmed);
      else await secrets.remove(API_KEY);
    },
  };
}

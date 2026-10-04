import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { settingsStore } from '../settings/nativeStorage';
import { DEFAULT_SETTINGS, type Settings } from '../settings/store';

interface AppState {
  ready: boolean;
  settings: Settings;
  apiKey: string;
  update(patch: Partial<Settings>): Promise<void>;
  setApiKey(value: string): Promise<void>;
  /** Always the latest values, for long-lived callbacks (controller, voice handlers). */
  getSettings(): Settings;
  getApiKey(): string;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS);
  const [apiKey, setApiKeyState] = useState('');
  const [ready, setReady] = useState(false);
  const settingsRef = useRef(settings);
  const keyRef = useRef(apiKey);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [loaded, key] = await Promise.all([settingsStore.load(), settingsStore.getApiKey()]);
      if (cancelled) return;
      settingsRef.current = loaded;
      keyRef.current = key;
      setSettings(loaded);
      setApiKeyState(key);
      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Updates run one at a time, each on top of the previous result: the settings fields save as you type, so two
  // updates can overlap, and an unserialised second one would be built on the old value and drop the first one's change.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const update = useCallback((patch: Partial<Settings>): Promise<void> => {
    const run = queue.current.then(async () => {
      const next = await settingsStore.save({ ...settingsRef.current, ...patch });
      settingsRef.current = next;
      setSettings(next);
    });
    queue.current = run.catch(() => undefined);
    return run;
  }, []);

  const setApiKey = useCallback(async (value: string) => {
    await settingsStore.setApiKey(value);
    keyRef.current = value.trim();
    setApiKeyState(value.trim());
  }, []);

  // Stable identities: long-lived objects (the analyze controller) capture these and must not be rebuilt on every change.
  const getSettings = useCallback(() => settingsRef.current, []);
  const getApiKey = useCallback(() => keyRef.current, []);

  const value = useMemo<AppState>(
    () => ({ ready, settings, apiKey, update, setApiKey, getSettings, getApiKey }),
    [ready, settings, apiKey, update, setApiKey, getSettings, getApiKey],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const value = useContext(AppContext);
  if (!value) throw new Error('useApp must be used inside AppProvider');
  return value;
}

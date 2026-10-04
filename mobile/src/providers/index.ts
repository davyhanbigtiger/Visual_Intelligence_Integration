import { ProviderError, type VisionProvider } from '../core/types';
import { remoteReadiness, type Settings } from '../settings/store';
import { createRemoteProvider } from './remote';

export interface ProviderFactoryDeps {
  getSettings(): Settings;
  getApiKey(): string;
  local: VisionProvider;
  fetchImpl?: typeof fetch;
}

/**
 * Picks the provider for the current settings at call time. It never falls back from one mode to the other:
 * a misconfigured remote mode is an error, not a silent switch to (or from) a different place pictures go.
 */
export function createProviderFactory(deps: ProviderFactoryDeps): () => VisionProvider {
  return () => {
    const settings = deps.getSettings();
    if (settings.mode === 'local') return deps.local;
    const ready = remoteReadiness(settings);
    if (!ready.ok) throw new ProviderError('not_configured', `The remote server is not ready (${ready.reason}).`);
    return createRemoteProvider({
      baseUrl: ready.baseUrl,
      apiKey: deps.getApiKey(),
      model: settings.remoteModel,
      fetchImpl: deps.fetchImpl,
    });
  };
}

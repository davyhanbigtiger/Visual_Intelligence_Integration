import type { ConfigContext, ExpoConfig } from 'expo/config';

/**
 * Dynamic parts of the configuration, driven by environment variables set per EAS build profile (see eas.json):
 *
 * - ALLOW_CLEARTEXT_ANDROID: "1" lets the Android app talk plain http (LAN / emulator testing). Never on in production.
 * - LLAMA_MEMORY_ENTITLEMENTS: "1" adds the iOS "increased memory limit" entitlements through llama.rn's plugin. They
 *   need matching capabilities on the App ID in your Apple developer account, so they are OFF for the first TestFlight
 *   build; use the "production-memory" profile once the plain build works.
 */
export default ({ config }: ConfigContext): ExpoConfig => {
  const isProduction = process.env.EAS_BUILD_PROFILE === 'production' || process.env.EAS_BUILD_PROFILE === 'production-memory';
  const cleartext = process.env.ALLOW_CLEARTEXT_ANDROID ? process.env.ALLOW_CLEARTEXT_ANDROID === '1' : !isProduction;
  const memoryEntitlements = process.env.LLAMA_MEMORY_ENTITLEMENTS === '1';

  return {
    ...config,
    name: config.name ?? 'Visual Helper',
    slug: config.slug ?? 'visual-helper',
    plugins: [
      ...(config.plugins ?? []),
      ['llama.rn', { enableEntitlements: memoryEntitlements, entitlementsProfile: ['production', 'production-memory'] }],
      ['expo-build-properties', { android: { usesCleartextTraffic: cleartext } }],
    ],
  };
};

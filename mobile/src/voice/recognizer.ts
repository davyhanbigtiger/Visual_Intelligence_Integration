import type { Language } from '../core/types';
import { COMMAND_HINTS, SPEECH_LOCALE } from './language';

export interface RecognizerHandlers {
  onPartial(text: string): void;
  onFinal(text: string): void;
  onError(code: string, message: string): void;
  onEnd(): void;
}

export type SpeechPrivacy = 'on_device' | 'maybe_cloud' | 'unavailable';

export interface Recognizer {
  /** False in builds without the native module (for example Expo Go): voice then simply stays off. */
  isAvailable(): boolean;
  requestPermission(): Promise<boolean>;
  /** Whether audio stays on the device for this language. Never promised: it depends on the installed language pack. */
  privacy(language: Language): Promise<SpeechPrivacy>;
  start(language: Language, handlers: RecognizerHandlers): void;
  /** Ends recording and delivers the final transcript. */
  stop(): void;
  abort(): void;
}

type NativeModule = typeof import('expo-speech-recognition').ExpoSpeechRecognitionModule;

function loadModule(): NativeModule | null {
  try {
    // Loaded lazily so a build without this native module still starts.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const mod = require('expo-speech-recognition') as typeof import('expo-speech-recognition');
    return mod.ExpoSpeechRecognitionModule ?? null;
  } catch {
    return null;
  }
}

/** Push-to-talk wrapper around expo-speech-recognition (iOS SFSpeechRecognizer / Android SpeechRecognizer). */
export function createRecognizer(): Recognizer {
  const mod = loadModule();
  let subscriptions: { remove(): void }[] = [];

  const cleanup = () => {
    subscriptions.forEach((s) => s.remove());
    subscriptions = [];
  };

  return {
    isAvailable() {
      try {
        return mod !== null && mod.isRecognitionAvailable();
      } catch {
        return false;
      }
    },
    async requestPermission() {
      if (!mod) return false;
      try {
        return (await mod.requestPermissionsAsync()).granted;
      } catch {
        return false;
      }
    },
    async privacy(language) {
      if (!mod) return 'unavailable';
      try {
        if (!mod.supportsOnDeviceRecognition()) return 'maybe_cloud';
        const { installedLocales } = await mod.getSupportedLocales({});
        const wanted = SPEECH_LOCALE[language].toLowerCase().replace('_', '-');
        return installedLocales.some((l) => l.toLowerCase().replace('_', '-') === wanted) ? 'on_device' : 'maybe_cloud';
      } catch {
        return 'maybe_cloud';
      }
    },
    start(language, handlers) {
      if (!mod) {
        handlers.onError('service-not-allowed', 'Speech recognition is not available in this build.');
        handlers.onEnd();
        return;
      }
      cleanup();
      subscriptions = [
        mod.addListener('result', (event) => {
          const text = event.results[0]?.transcript ?? '';
          if (event.isFinal) handlers.onFinal(text);
          else handlers.onPartial(text);
        }),
        mod.addListener('error', (event) => handlers.onError(event.error, event.message)),
        mod.addListener('end', () => {
          cleanup();
          handlers.onEnd();
        }),
      ];
      mod.start({
        lang: SPEECH_LOCALE[language],
        interimResults: true,
        continuous: false,
        // Keep audio on the device whenever the device and language pack allow it.
        requiresOnDeviceRecognition: true,
        contextualStrings: COMMAND_HINTS[language],
      });
    },
    stop() {
      mod?.stop();
    },
    abort() {
      mod?.abort();
      cleanup();
    },
  };
}

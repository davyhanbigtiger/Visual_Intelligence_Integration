import {
  ProviderError,
  type EncodedImage,
  type Language,
  type ProviderId,
  type ProviderErrorKind,
  type VisionProvider,
} from '../core/types';
import { errorMessage } from '../i18n/strings';
import { planSpeech, type SpeechPlan } from '../safety/policy';

export interface CapturedPhoto {
  uri: string;
  width: number;
  height: number;
}
export interface CameraPort {
  capture(): Promise<CapturedPhoto>;
}
export interface ImageEncoderPort {
  /** Re-encode as JPEG with the longest side at most `maxSide` (never upscales). */
  encode(photo: CapturedPhoto, maxSide: number): Promise<EncodedImage>;
}
export interface SpeakerPort {
  speak(text: string, language: Language): Promise<void>;
  stop(): void;
}

export type ControllerState =
  | { phase: 'idle' }
  | { phase: 'capturing' }
  | { phase: 'thinking'; provider: ProviderId }
  | { phase: 'done'; plan: SpeechPlan; latencyMs: number; provider: ProviderId }
  | { phase: 'error'; kind: ProviderErrorKind | 'camera' | 'unknown'; message: string };

export interface ControllerDeps {
  getProvider(): VisionProvider;
  camera: CameraPort;
  encoder: ImageEncoderPort;
  speaker: SpeakerPort;
  getSettings(): { language: Language; speakResults: boolean };
  onState(state: ControllerState): void;
  /** First attempt and the retry size (the retry changes the pixels, because some failures repeat for identical input). */
  sizes?: readonly [number, number];
  now?: () => number;
}

export interface AnalyzeController {
  analyze(): Promise<void>;
  repeat(): Promise<void>;
  stopSpeaking(): void;
  cancel(): void;
  isBusy(): boolean;
}

export function createAnalyzeController(deps: ControllerDeps): AnalyzeController {
  const sizes = deps.sizes ?? [640, 592];
  const now = deps.now ?? Date.now;
  let busy = false;
  let abort: AbortController | null = null;
  let disclaimerSpoken = false;
  let lastSpoken: { text: string; language: Language } | null = null;

  async function speakText(text: string, language: Language): Promise<void> {
    lastSpoken = { text, language };
    try {
      await deps.speaker.speak(text, language);
    } catch {
      // Speech output failing must not hide the on-screen result.
    }
  }

  async function analyze(): Promise<void> {
    if (busy) return;
    busy = true;
    abort = new AbortController();
    deps.speaker.stop();
    const { language, speakResults } = deps.getSettings();
    const started = now();
    try {
      deps.onState({ phase: 'capturing' });
      let photo: CapturedPhoto;
      try {
        photo = await deps.camera.capture();
      } catch {
        deps.onState({ phase: 'error', kind: 'camera', message: errorMessage('camera', language) });
        return;
      }
      const provider = deps.getProvider();
      deps.onState({ phase: 'thinking', provider: provider.id });
      let outcome;
      try {
        outcome = await provider.analyze(await deps.encoder.encode(photo, sizes[0]), {
          language,
          signal: abort.signal,
        });
      } catch (error) {
        if (!(error instanceof ProviderError) || error.kind !== 'invalid_output') throw error;
        // Some inputs make a model produce unusable text deterministically; the same pixels would fail again.
        outcome = await provider.analyze(await deps.encoder.encode(photo, sizes[1]), {
          language,
          signal: abort.signal,
        });
      }
      const plan = planSpeech(outcome.result, language, { firstInSession: !disclaimerSpoken });
      if (plan.disclaimer) disclaimerSpoken = true;
      deps.onState({ phase: 'done', plan, latencyMs: now() - started, provider: provider.id });
      if (speakResults) await speakText(plan.spoken.join(' '), language);
    } catch (error) {
      const kind: ProviderErrorKind | 'unknown' = error instanceof ProviderError ? error.kind : 'unknown';
      deps.onState({ phase: 'error', kind, message: errorMessage(kind, language) });
    } finally {
      busy = false;
      abort = null;
    }
  }

  return {
    analyze,
    async repeat() {
      if (lastSpoken) {
        deps.speaker.stop();
        await speakText(lastSpoken.text, lastSpoken.language);
      }
    },
    stopSpeaking() {
      deps.speaker.stop();
    },
    cancel() {
      abort?.abort();
    },
    isBusy() {
      return busy;
    },
  };
}

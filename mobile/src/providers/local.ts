import { buildPrompt, parseSceneResult, SCENE_SCHEMA } from '../core/scene';
import { ProviderError, type ProviderResult, type VisionProvider } from '../core/types';

/** The few things we need from an on-device multimodal runtime (llama.rn in production, a fake in tests). */
export interface LlamaPort {
  load(): Promise<void>;
  complete(args: { prompt: string; imageUri: string; schema: object; maxTokens: number }): Promise<string>;
  /** Best-effort: stop a running completion. */
  stop(): Promise<void>;
  release(): Promise<void>;
}

/**
 * How long one on-device analysis (model load + inference) may take before it is stopped. Generous on purpose: a first
 * load on a slow phone is long. On an x86 emulator (2 vCPU, no GPU) one frame took well over ten minutes, which with
 * no limit looked like a hang.
 */
export const DEFAULT_LOCAL_TIMEOUT_MS = 120_000;

export interface LocalProviderOptions {
  now?: () => number;
  timeoutMs?: number;
}

export function createLocalProvider(port: LlamaPort, isModelReady: () => boolean, options: LocalProviderOptions = {}): VisionProvider {
  const now = options.now ?? Date.now;
  const timeoutMs = options.timeoutMs ?? DEFAULT_LOCAL_TIMEOUT_MS;
  let loading: Promise<void> | null = null;
  let loaded = false;

  async function ensureLoaded(): Promise<void> {
    if (loaded) return;
    loading ??= port.load().then(
      () => {
        loaded = true;
      },
      (error) => {
        loading = null; // allow a later retry
        throw new ProviderError('not_ready', `The on-device model could not be loaded: ${(error as Error)?.message ?? 'unknown error'}`);
      },
    );
    await loading;
  }

  return {
    id: 'local',
    async analyze(image, ctx): Promise<ProviderResult> {
      if (ctx.signal?.aborted) throw new ProviderError('cancelled', 'The request was cancelled.');
      if (!isModelReady()) throw new ProviderError('not_ready', 'The on-device model has not been downloaded.');
      const started = now();

      let timedOut = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const limit = new Promise<never>((_resolve, reject) => {
        timer = setTimeout(() => {
          timedOut = true;
          void port.stop().catch(() => undefined);
          reject(new ProviderError('too_slow', 'The on-device model did not finish in time.'));
        }, timeoutMs);
      });
      const onAbort = () => {
        void port.stop().catch(() => undefined);
      };
      ctx.signal?.addEventListener('abort', onAbort, { once: true });

      let text: string;
      try {
        const work = (async () => {
          await ensureLoaded();
          if (ctx.signal?.aborted) throw new ProviderError('cancelled', 'The request was cancelled.');
          return port.complete({
            prompt: buildPrompt(ctx.language),
            imageUri: image.uri,
            schema: SCENE_SCHEMA,
            maxTokens: 160,
          });
        })();
        work.catch(() => undefined); // if the time limit wins, nobody awaits this any more
        text = await Promise.race([work, limit]);
      } catch (error) {
        if (error instanceof ProviderError) throw error;
        if (ctx.signal?.aborted && !timedOut) throw new ProviderError('cancelled', 'The request was cancelled.');
        throw new ProviderError('server', `On-device inference failed: ${(error as Error)?.message ?? 'unknown error'}`);
      } finally {
        clearTimeout(timer);
        ctx.signal?.removeEventListener('abort', onAbort);
      }
      return { result: parseSceneResult(text), rawText: text, latencyMs: now() - started, provider: 'local' };
    },
  };
}

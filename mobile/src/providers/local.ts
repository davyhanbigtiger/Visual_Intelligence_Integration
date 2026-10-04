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

export function createLocalProvider(port: LlamaPort, isModelReady: () => boolean, now: () => number = Date.now): VisionProvider {
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
      await ensureLoaded();
      const onAbort = () => {
        void port.stop().catch(() => undefined);
      };
      ctx.signal?.addEventListener('abort', onAbort, { once: true });
      let text: string;
      try {
        text = await port.complete({
          prompt: buildPrompt(ctx.language),
          imageUri: image.uri,
          schema: SCENE_SCHEMA,
          maxTokens: 160,
        });
      } catch (error) {
        if (ctx.signal?.aborted) throw new ProviderError('cancelled', 'The request was cancelled.');
        if (error instanceof ProviderError) throw error;
        throw new ProviderError('server', `On-device inference failed: ${(error as Error)?.message ?? 'unknown error'}`);
      } finally {
        ctx.signal?.removeEventListener('abort', onAbort);
      }
      return { result: parseSceneResult(text), rawText: text, latencyMs: now() - started, provider: 'local' };
    },
  };
}

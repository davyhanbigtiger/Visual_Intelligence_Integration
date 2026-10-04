import { TurboModuleRegistry } from 'react-native';

import type { LlamaPort } from './local';

type LlamaRn = typeof import('llama.rn');
type Context = Awaited<ReturnType<LlamaRn['initLlama']>>;

function stripFileScheme(path: string): string {
  return path.replace(/^file:\/\//, '');
}

/**
 * llama.rn glue. NOT verified on a device: written against llama.rn 0.12.9's README/types, where multimodal needs
 * `ctx_shift: false`, `initMultimodal({ path, use_gpu })` and image content as `image_url`.
 * llama.rn is loaded lazily so a build without the native module still starts (the local mode then reports not_ready).
 */
export function createLlamaRnPort(paths: { model: string; mmproj: string }): LlamaPort {
  let context: Context | null = null;

  return {
    async load() {
      if (context) return;
      // llama.rn looks its native half up with the non-throwing `get`; without it (Expo Go) initLlama would fail
      // with an obscure TypeError, so say clearly what is missing.
      if (!TurboModuleRegistry.get('RNLlama')) throw new Error('The on-device AI runtime is not part of this build.');
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      const { initLlama } = require('llama.rn') as LlamaRn;
      const created = await initLlama({
        model: stripFileScheme(paths.model),
        n_ctx: 2048,
        n_gpu_layers: 99,
        ctx_shift: false,
      });
      const ok = await created.initMultimodal({ path: stripFileScheme(paths.mmproj), use_gpu: true });
      if (!ok) {
        await created.release();
        throw new Error('The vision projector could not be initialised.');
      }
      context = created;
    },
    async complete({ prompt, imageUri, schema, maxTokens }) {
      if (!context) throw new Error('The model is not loaded.');
      const result = await context.completion({
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              { type: 'image_url', image_url: { url: imageUri } },
            ],
          },
        ],
        n_predict: maxTokens,
        temperature: 0,
        enable_thinking: false,
        response_format: { type: 'json_schema', json_schema: { schema } },
      });
      return result.text;
    },
    async stop() {
      await context?.stopCompletion();
    },
    async release() {
      if (!context) return;
      const current = context;
      context = null;
      await current.releaseMultimodal();
      await current.release();
    },
  };
}

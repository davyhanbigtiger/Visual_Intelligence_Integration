import { buildPrompt, parseSceneResult, SCENE_SCHEMA } from '../core/scene';
import {
  ProviderError,
  type AnalyzeContext,
  type EncodedImage,
  type ProviderResult,
  type VisionProvider,
} from '../core/types';

export interface RemoteOptions {
  /** Normalised base URL, e.g. https://gpu.example.com (see settings/validate.ts). */
  baseUrl: string;
  apiKey?: string;
  model?: string;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
  now?: () => number;
}

// A GPU server answers in about a second, but a CPU / integrated-GPU box on the local network takes 8-17 s, and the first
// request after a model starts takes longer still (observed 30+ s on the emulator test, 2026-10-04). 60 s avoids
// reporting a healthy but slow server as broken; the UI shows "looking..." meanwhile.
const DEFAULT_TIMEOUT_MS = 60_000;

function headers(apiKey?: string): Record<string, string> {
  const base: Record<string, string> = { 'Content-Type': 'application/json' };
  if (apiKey) base.Authorization = `Bearer ${apiKey}`;
  return base;
}

export function buildChatPayload(model: string, image: EncodedImage, language: AnalyzeContext['language']) {
  return {
    model,
    temperature: 0,
    seed: 42,
    max_tokens: 160,
    messages: [
      {
        role: 'user',
        content: [
          { type: 'text', text: buildPrompt(language) },
          { type: 'image_url', image_url: { url: `data:image/jpeg;base64,${image.base64}` } },
        ],
      },
    ],
    response_format: { type: 'json_schema', json_schema: { name: 'scene', schema: SCENE_SCHEMA } },
  };
}

/** Never put the response body (could echo a prompt) or the key in an error; keep a short, safe snippet. */
function snippet(body: string): string {
  return body.replace(/\s+/g, ' ').slice(0, 120);
}

async function request(
  fetchImpl: typeof fetch,
  url: string,
  init: RequestInit,
  timeoutMs: number,
  outer?: AbortSignal,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const onOuterAbort = () => controller.abort();
  if (outer) {
    if (outer.aborted) controller.abort();
    else outer.addEventListener('abort', onOuterAbort, { once: true });
  }
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new ProviderError('timeout', 'The server did not answer in time.');
    if (outer?.aborted) throw new ProviderError('cancelled', 'The request was cancelled.');
    throw new ProviderError('network', `Cannot reach the server (${(error as Error)?.message ?? 'network error'}).`);
  } finally {
    clearTimeout(timer);
    outer?.removeEventListener('abort', onOuterAbort);
  }
}

export function createRemoteProvider(options: RemoteOptions): VisionProvider {
  const fetchImpl = options.fetchImpl ?? fetch;
  const now = options.now ?? Date.now;
  const model = options.model || 'minicpm-v4.6';
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  return {
    id: 'remote',
    async analyze(image, ctx): Promise<ProviderResult> {
      const started = now();
      const response = await request(
        fetchImpl,
        `${options.baseUrl}/v1/chat/completions`,
        {
          method: 'POST',
          headers: headers(options.apiKey),
          body: JSON.stringify(buildChatPayload(model, image, ctx.language)),
        },
        timeoutMs,
        ctx.signal,
      );
      const body = await response.text();
      if (response.status === 401 || response.status === 403) {
        throw new ProviderError('auth', 'The server rejected the API key.', response.status);
      }
      if (!response.ok) {
        throw new ProviderError('server', `Server error ${response.status}: ${snippet(body)}`, response.status);
      }
      let data: { choices?: { message?: { content?: unknown }; finish_reason?: string }[] };
      try {
        data = JSON.parse(body);
      } catch {
        throw new ProviderError('invalid_output', 'The server answered with something that is not JSON.');
      }
      const choice = data.choices?.[0];
      const content = choice?.message?.content;
      if (typeof content !== 'string' || !content.trim()) {
        throw new ProviderError('invalid_output', 'The server returned an empty answer.');
      }
      if (choice?.finish_reason === 'length') {
        throw new ProviderError('invalid_output', 'The answer was cut off before it finished.');
      }
      return { result: parseSceneResult(content), rawText: content, latencyMs: now() - started, provider: 'remote' };
    },
  };
}

export interface ConnectionCheck {
  ok: boolean;
  detail: 'ok' | 'auth' | 'unreachable' | 'timeout' | 'unexpected';
  status?: number;
}

/** Cheap reachability check: llama-server answers /health; OpenAI-style servers answer /v1/models. */
export async function testConnection(
  baseUrl: string,
  apiKey?: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 8000,
): Promise<ConnectionCheck> {
  for (const path of ['/health', '/v1/models']) {
    try {
      const response = await request(fetchImpl, `${baseUrl}${path}`, { method: 'GET', headers: headers(apiKey) }, timeoutMs);
      if (response.status === 401 || response.status === 403) return { ok: false, detail: 'auth', status: response.status };
      if (response.ok) return { ok: true, detail: 'ok', status: response.status };
      if (response.status !== 404) return { ok: false, detail: 'unexpected', status: response.status };
    } catch (error) {
      if (error instanceof ProviderError && error.kind === 'timeout') return { ok: false, detail: 'timeout' };
      return { ok: false, detail: 'unreachable' };
    }
  }
  return { ok: false, detail: 'unexpected', status: 404 };
}

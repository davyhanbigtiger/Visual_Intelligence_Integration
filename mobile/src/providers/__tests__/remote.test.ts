import { ProviderError, type EncodedImage } from '../../core/types';
import { buildChatPayload, createRemoteProvider, testConnection } from '../remote';

const image: EncodedImage = { uri: 'file:///x.jpg', base64: 'QUJD', width: 640, height: 480 };
const goodContent = JSON.stringify({ answer: 'A quiet street.', scene: 'road', hazard: 'none', hazard_confidence: 'high' });

function reply(status: number, body: unknown) {
  return Promise.resolve(new Response(typeof body === 'string' ? body : JSON.stringify(body), { status }));
}
const okBody = (content = goodContent, finish = 'stop') => ({ choices: [{ message: { content }, finish_reason: finish }] });

type FetchArgs = [string, RequestInit];
function recorder(handler: (url: string, init: RequestInit) => Promise<Response>) {
  const calls: FetchArgs[] = [];
  const fetchImpl = ((url: string, init: RequestInit) => {
    calls.push([url, init]);
    return handler(url, init);
  }) as unknown as typeof fetch;
  return { calls, fetchImpl };
}

async function kindOf(promise: Promise<unknown>): Promise<string> {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ProviderError) return error.kind;
    throw error;
  }
  return 'resolved';
}

describe('createRemoteProvider', () => {
  it('posts an OpenAI-style request with the image, schema and bearer key, and parses the result', async () => {
    const { calls, fetchImpl } = recorder(() => reply(200, okBody()));
    const provider = createRemoteProvider({ baseUrl: 'https://gpu.example.com', apiKey: 'secret-key', fetchImpl });
    const out = await provider.analyze(image, { language: 'zh' });

    expect(out.provider).toBe('remote');
    expect(out.result).toEqual({ answer: 'A quiet street.', scene: 'road', hazard: 'none', hazardConfidence: 'high' });
    const [url, init] = calls[0];
    expect(url).toBe('https://gpu.example.com/v1/chat/completions');
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer secret-key');
    const body = JSON.parse(init.body as string);
    expect(body.model).toBe('minicpm-v4.6');
    expect(body.temperature).toBe(0);
    expect(body.response_format.type).toBe('json_schema');
    expect(body.messages[0].content[1].image_url.url).toBe('data:image/jpeg;base64,QUJD');
    expect(body.messages[0].content[0].text).toContain('Simplified Chinese');
  });

  it('sends no Authorization header when there is no key', async () => {
    const { calls, fetchImpl } = recorder(() => reply(200, okBody()));
    await createRemoteProvider({ baseUrl: 'http://10.0.2.2:18937', fetchImpl }).analyze(image, { language: 'en' });
    expect((calls[0][1].headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('maps HTTP and body problems to the right error kinds', async () => {
    const cases: Array<[string, () => Promise<Response>]> = [
      ['auth', () => reply(401, 'no')],
      ['auth', () => reply(403, 'no')],
      ['server', () => reply(500, 'boom')],
      ['server', () => reply(404, 'not found')],
      ['invalid_output', () => reply(200, 'this is not json')],
      ['invalid_output', () => reply(200, { choices: [] })],
      ['invalid_output', () => reply(200, okBody('  '))],
      ['invalid_output', () => reply(200, okBody('{"answer": "cut', 'length'))],
      ['invalid_output', () => reply(200, okBody('tennis court100 211 998 989'))],
    ];
    for (const [kind, handler] of cases) {
      const { fetchImpl } = recorder(handler);
      const provider = createRemoteProvider({ baseUrl: 'https://h.example', fetchImpl });
      expect(await kindOf(provider.analyze(image, { language: 'en' }))).toBe(kind);
    }
  });

  it('reports a network failure and never leaks the key into the message', async () => {
    const { fetchImpl } = recorder(() => Promise.reject(new TypeError('Network request failed')));
    const provider = createRemoteProvider({ baseUrl: 'https://h.example', apiKey: 'secret-key', fetchImpl });
    const error = await provider.analyze(image, { language: 'en' }).catch((e) => e as ProviderError);
    expect(error).toBeInstanceOf(ProviderError);
    expect(error.kind).toBe('network');
    expect(error.message).not.toContain('secret-key');
  });

  it('keeps server error snippets short and free of the key', async () => {
    const { fetchImpl } = recorder(() => reply(500, 'x'.repeat(5000)));
    const provider = createRemoteProvider({ baseUrl: 'https://h.example', apiKey: 'secret-key', fetchImpl });
    const error = (await provider.analyze(image, { language: 'en' }).catch((e) => e)) as ProviderError;
    expect(error.message.length).toBeLessThan(200);
    expect(error.message).not.toContain('secret-key');
  });

  it('times out when the server never answers', async () => {
    const { fetchImpl } = recorder(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    );
    const provider = createRemoteProvider({ baseUrl: 'https://h.example', fetchImpl, timeoutMs: 20 });
    expect(await kindOf(provider.analyze(image, { language: 'en' }))).toBe('timeout');
  });

  it('reports cancelled when the caller aborts', async () => {
    const controller = new AbortController();
    const { fetchImpl } = recorder(
      (_url, init) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => reject(new Error('aborted')));
        }),
    );
    const provider = createRemoteProvider({ baseUrl: 'https://h.example', fetchImpl, timeoutMs: 5000 });
    const pending = provider.analyze(image, { language: 'en', signal: controller.signal });
    controller.abort();
    expect(await kindOf(pending)).toBe('cancelled');
  });

  it('measures latency with the injected clock', async () => {
    let t = 1000;
    const { fetchImpl } = recorder(() => {
      t += 850;
      return reply(200, okBody());
    });
    const provider = createRemoteProvider({ baseUrl: 'https://h.example', fetchImpl, now: () => t });
    expect((await provider.analyze(image, { language: 'en' })).latencyMs).toBe(850);
  });
});

describe('buildChatPayload', () => {
  it('uses the requested model name', () => {
    expect(buildChatPayload('my-model', image, 'en').model).toBe('my-model');
  });
});

describe('testConnection', () => {
  it('is ok when /health answers', async () => {
    const { calls, fetchImpl } = recorder(() => reply(200, { status: 'ok' }));
    expect(await testConnection('https://h.example', undefined, fetchImpl)).toEqual({ ok: true, detail: 'ok', status: 200 });
    expect(calls[0][0]).toBe('https://h.example/health');
  });

  it('falls back to /v1/models when /health does not exist', async () => {
    const { calls, fetchImpl } = recorder((url) => (url.endsWith('/health') ? reply(404, 'nope') : reply(200, { data: [] })));
    expect((await testConnection('https://h.example', 'k', fetchImpl)).ok).toBe(true);
    expect(calls.map((c) => c[0])).toEqual(['https://h.example/health', 'https://h.example/v1/models']);
  });

  it('distinguishes auth, unexpected status, unreachable and timeout', async () => {
    expect((await testConnection('https://h', 'k', recorder(() => reply(401, '')).fetchImpl)).detail).toBe('auth');
    expect((await testConnection('https://h', 'k', recorder(() => reply(500, '')).fetchImpl)).detail).toBe('unexpected');
    expect((await testConnection('https://h', undefined, recorder(() => Promise.reject(new TypeError('x'))).fetchImpl)).detail).toBe(
      'unreachable',
    );
    const hang = recorder((_u, init) => new Promise<Response>((_r, rej) => init.signal?.addEventListener('abort', () => rej(new Error('a')))));
    expect((await testConnection('https://h', undefined, hang.fetchImpl, 20)).detail).toBe('timeout');
  });
});

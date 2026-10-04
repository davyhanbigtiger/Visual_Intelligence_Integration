import { ProviderError, type EncodedImage } from '../../core/types';
import { createLocalProvider, type LlamaPort } from '../local';
import { createProviderFactory } from '../index';
import {
  deviceFit,
  downloadModel,
  fileState,
  LOCAL_MODEL,
  modelStatus,
  type ModelFileSpec,
  type ModelFilesPort,
} from '../localModel';
import { DEFAULT_SETTINGS, type Settings } from '../../settings/store';

const image: EncodedImage = { uri: 'file:///cache/x.jpg', base64: 'QUJD', width: 640, height: 480 };
const goodText = JSON.stringify({ answer: 'A beach.', scene: 'beach', hazard: 'none', hazard_confidence: 'high' });

function fakePort(overrides: Partial<LlamaPort> = {}) {
  const calls = { load: 0, complete: [] as { prompt: string; imageUri: string; maxTokens: number }[], stop: 0 };
  const port: LlamaPort = {
    async load() {
      calls.load += 1;
    },
    async complete(args) {
      calls.complete.push({ prompt: args.prompt, imageUri: args.imageUri, maxTokens: args.maxTokens });
      return goodText;
    },
    async stop() {
      calls.stop += 1;
    },
    async release() {},
    ...overrides,
  };
  return { port, calls };
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

describe('createLocalProvider', () => {
  it('loads once, passes the file URI (not base64), and parses the result', async () => {
    const { port, calls } = fakePort();
    const provider = createLocalProvider(port, () => true);
    const first = await provider.analyze(image, { language: 'zh' });
    await provider.analyze(image, { language: 'zh' });
    expect(first.provider).toBe('local');
    expect(first.result.scene).toBe('beach');
    expect(calls.load).toBe(1);
    expect(calls.complete[0].imageUri).toBe('file:///cache/x.jpg');
    expect(calls.complete[0].prompt).toContain('Simplified Chinese');
  });

  it('shares a single load between concurrent first calls', async () => {
    let release: () => void = () => undefined;
    const { port, calls } = fakePort({
      load: () => new Promise<void>((resolve) => (release = resolve)).then(() => undefined),
    });
    const provider = createLocalProvider(port, () => true);
    const a = provider.analyze(image, { language: 'en' });
    const b = provider.analyze(image, { language: 'en' });
    await Promise.resolve();
    release();
    await Promise.all([a, b]);
    expect(calls.complete).toHaveLength(2);
  });

  it('is not_ready when the model files are missing, without loading anything', async () => {
    const { port, calls } = fakePort();
    const provider = createLocalProvider(port, () => false);
    expect(await kindOf(provider.analyze(image, { language: 'en' }))).toBe('not_ready');
    expect(calls.load).toBe(0);
  });

  it('turns a failed load into not_ready, and can retry the load later', async () => {
    let attempts = 0;
    const { port } = fakePort({
      load: async () => {
        attempts += 1;
        if (attempts === 1) throw new Error('out of memory');
      },
    });
    const provider = createLocalProvider(port, () => true);
    expect(await kindOf(provider.analyze(image, { language: 'en' }))).toBe('not_ready');
    expect(await kindOf(provider.analyze(image, { language: 'en' }))).toBe('resolved');
    expect(attempts).toBe(2);
  });

  it('maps unusable output to invalid_output and runtime failures to server', async () => {
    const bad = createLocalProvider(fakePort({ complete: async () => 'tennis court100 211 998' }).port, () => true);
    expect(await kindOf(bad.analyze(image, { language: 'en' }))).toBe('invalid_output');
    const broken = createLocalProvider(
      fakePort({
        complete: async () => {
          throw new Error('metal failure');
        },
      }).port,
      () => true,
    );
    expect(await kindOf(broken.analyze(image, { language: 'en' }))).toBe('server');
  });

  it('stops the runtime and reports cancelled when aborted', async () => {
    const controller = new AbortController();
    let rejectCompletion: (e: Error) => void = () => undefined;
    const { port, calls } = fakePort({
      complete: () => new Promise<string>((_resolve, reject) => (rejectCompletion = reject)),
      stop: async () => {
        calls.stop += 1;
        rejectCompletion(new Error('stopped'));
      },
    });
    const provider = createLocalProvider(port, () => true);
    const pending = provider.analyze(image, { language: 'en', signal: controller.signal });
    await new Promise((r) => setTimeout(r, 0));
    controller.abort();
    expect(await kindOf(pending)).toBe('cancelled');
    expect(calls.stop).toBe(1);
  });

  it('refuses to start when already aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    const { port, calls } = fakePort();
    const provider = createLocalProvider(port, () => true);
    expect(await kindOf(provider.analyze(image, { language: 'en', signal: controller.signal }))).toBe('cancelled');
    expect(calls.load).toBe(0);
  });
});

function memoryFiles(initial: Record<string, number> = {}, behaviour: { shortWrite?: boolean } = {}) {
  const sizes: Record<string, number> = { ...initial };
  const downloads: string[] = [];
  const removed: string[] = [];
  const files: ModelFilesPort = {
    size: (name) => (name in sizes ? sizes[name] : null),
    path: (name) => `file:///cache/models/${name}`,
    remove: (name) => {
      removed.push(name);
      delete sizes[name];
    },
    async download(spec: ModelFileSpec, onProgress) {
      downloads.push(spec.name);
      onProgress(spec.bytes / 2, spec.bytes);
      sizes[spec.name] = behaviour.shortWrite ? spec.bytes - 1 : spec.bytes;
      onProgress(spec.bytes, spec.bytes);
    },
  };
  return { files, downloads, removed, sizes };
}

describe('model files', () => {
  it('classifies files by exact size', () => {
    const spec = LOCAL_MODEL.main;
    expect(fileState(null, spec)).toBe('missing');
    expect(fileState(0, spec)).toBe('missing');
    expect(fileState(spec.bytes - 1, spec)).toBe('partial');
    expect(fileState(spec.bytes, spec)).toBe('ready');
    expect(fileState(spec.bytes + 1, spec)).toBe('partial');
  });

  it('uses the public repository URLs and the byte sizes verified earlier', () => {
    expect(LOCAL_MODEL.main.url).toBe('https://huggingface.co/ggml-org/MiniCPM-V-4.6-GGUF/resolve/main/MiniCPM-V-4.6-Q4_K_M.gguf');
    expect(LOCAL_MODEL.main.bytes).toBe(529101536);
    expect(LOCAL_MODEL.mmproj.bytes).toBe(727954528);
  });

  it('reports status', () => {
    expect(modelStatus(memoryFiles().files).ready).toBe(false);
    const ready = memoryFiles({ [LOCAL_MODEL.main.name]: LOCAL_MODEL.main.bytes, [LOCAL_MODEL.mmproj.name]: LOCAL_MODEL.mmproj.bytes });
    expect(modelStatus(ready.files)).toMatchObject({ main: 'ready', mmproj: 'ready', ready: true });
  });

  it('downloads missing files in order with monotonic progress, and skips files that are ready', async () => {
    const { files, downloads } = memoryFiles({ [LOCAL_MODEL.main.name]: LOCAL_MODEL.main.bytes });
    const seen: number[] = [];
    await downloadModel(files, (f) => seen.push(f));
    expect(downloads).toEqual([LOCAL_MODEL.mmproj.name]);
    expect(seen[seen.length - 1]).toBeCloseTo(1, 5);
    for (let i = 1; i < seen.length; i += 1) expect(seen[i]).toBeGreaterThanOrEqual(seen[i - 1]);
    expect(modelStatus(files).ready).toBe(true);
  });

  it('removes a partial file before downloading it again', async () => {
    const { files, downloads, removed } = memoryFiles({ [LOCAL_MODEL.main.name]: 1234 });
    await downloadModel(files, () => undefined);
    expect(removed).toContain(LOCAL_MODEL.main.name);
    expect(downloads).toEqual([LOCAL_MODEL.main.name, LOCAL_MODEL.mmproj.name]);
  });

  it('fails and removes the file when the downloaded size is wrong', async () => {
    const { files, removed } = memoryFiles({}, { shortWrite: true });
    await expect(downloadModel(files, () => undefined)).rejects.toThrow(/wrong size/);
    expect(removed).toContain(LOCAL_MODEL.main.name);
    expect(modelStatus(files).ready).toBe(false);
  });
});

describe('deviceFit', () => {
  it.each([
    [null, 'unknown'],
    [0, 'unknown'],
    [3.0e9, 'too_small'],
    [4.0e9, 'tight'],
    [5.4e9, 'tight'],
    [5.7e9, 'ok'],
    [8.0e9, 'ok'],
  ] as const)('%s bytes -> %s', (bytes, fit) => {
    expect(deviceFit(bytes)).toBe(fit);
  });
});

describe('createProviderFactory', () => {
  const local = { id: 'local' as const, analyze: async () => Promise.reject(new Error('unused')) };
  const make = (settings: Partial<Settings>, apiKey = '') =>
    createProviderFactory({ getSettings: () => ({ ...DEFAULT_SETTINGS, ...settings }), getApiKey: () => apiKey, local });

  it('returns the local provider in local mode', () => {
    expect(make({ mode: 'local' })()).toBe(local);
  });

  it('builds a remote provider only with a valid URL and explicit consent', () => {
    expect(make({ mode: 'remote', remoteUrl: 'https://gpu.example.com', remoteConsent: true })().id).toBe('remote');
    for (const bad of [
      { remoteUrl: '', remoteConsent: true },
      { remoteUrl: 'http://example.com', remoteConsent: true },
      { remoteUrl: 'https://gpu.example.com', remoteConsent: false },
      { remoteUrl: 'nonsense', remoteConsent: true },
    ]) {
      expect(() => make({ mode: 'remote', ...bad })()).toThrow(ProviderError);
      try {
        make({ mode: 'remote', ...bad })();
      } catch (error) {
        expect((error as ProviderError).kind).toBe('not_configured');
      }
    }
  });

  it('never falls back to local when remote is misconfigured', () => {
    expect(() => make({ mode: 'remote', remoteUrl: '', remoteConsent: true })()).toThrow();
  });
});

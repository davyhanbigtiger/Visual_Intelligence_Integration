import {
  ProviderError,
  type AnalyzeContext,
  type EncodedImage,
  type Language,
  type ProviderResult,
  type SceneResult,
  type VisionProvider,
} from '../../core/types';
import { PHRASES } from '../../safety/phrases';
import { createAnalyzeController, type ControllerState } from '../analyze';

const scene: SceneResult = { answer: 'A bear on grass.', hazard: 'animal' };

function setup(overrides: { provider?: Partial<VisionProvider>; speakResults?: boolean; language?: Language } = {}) {
  const states: ControllerState[] = [];
  const spoken: string[] = [];
  const encodes: number[] = [];
  const analyzeCalls: AnalyzeContext[] = [];
  let stops = 0;
  const provider: VisionProvider = {
    id: 'remote',
    async analyze(_image, ctx): Promise<ProviderResult> {
      analyzeCalls.push(ctx);
      return { result: scene, rawText: '{}', latencyMs: 5, provider: 'remote' };
    },
    ...overrides.provider,
  };
  let clock = 0;
  const controller = createAnalyzeController({
    getProvider: () => provider,
    camera: { capture: async () => ({ uri: 'file:///photo.jpg', width: 1920, height: 1080 }) },
    encoder: {
      encode: async (photo, maxSide): Promise<EncodedImage> => {
        encodes.push(maxSide);
        return { uri: photo.uri, base64: 'QUJD', width: maxSide, height: maxSide };
      },
    },
    speaker: {
      speak: async (text) => {
        spoken.push(text);
      },
      stop: () => {
        stops += 1;
      },
    },
    getSettings: () => ({ language: overrides.language ?? 'en', speakResults: overrides.speakResults ?? true }),
    onState: (s) => states.push(s),
    now: () => (clock += 100),
  });
  return { controller, states, spoken, encodes, analyzeCalls, stops: () => stops };
}

describe('analyze controller', () => {
  it('captures, thinks, completes and speaks the alert first, with the disclaimer only once', async () => {
    const t = setup();
    await t.controller.analyze();
    expect(t.states.map((s) => s.phase)).toEqual(['capturing', 'thinking', 'done']);
    expect(t.spoken[0].startsWith(PHRASES.en.hazard.animal)).toBe(true);
    expect(t.spoken[0]).toContain('A bear on grass.');
    expect(t.spoken[0]).toContain(PHRASES.en.disclaimer);
    await t.controller.analyze();
    expect(t.spoken[1]).not.toContain(PHRASES.en.disclaimer);
    expect(t.encodes).toEqual([640, 640]);
  });

  it('reports elapsed time and which provider answered', async () => {
    const t = setup();
    await t.controller.analyze();
    const done = t.states.find((s) => s.phase === 'done');
    expect(done).toMatchObject({ phase: 'done', provider: 'remote' });
    expect((done as { latencyMs: number }).latencyMs).toBeGreaterThan(0);
  });

  it('retries once at a different size when the output is unusable, then succeeds', async () => {
    let calls = 0;
    const t = setup({
      provider: {
        analyze: async (): Promise<ProviderResult> => {
          calls += 1;
          if (calls === 1) throw new ProviderError('invalid_output', 'garbage');
          return { result: scene, rawText: '{}', latencyMs: 5, provider: 'remote' };
        },
      },
    });
    await t.controller.analyze();
    expect(t.encodes).toEqual([640, 592]);
    expect(t.states[t.states.length - 1].phase).toBe('done');
  });

  it('gives up honestly after a second unusable output and speaks nothing it could have guessed', async () => {
    const t = setup({
      provider: {
        analyze: async () => {
          throw new ProviderError('invalid_output', 'garbage');
        },
      },
    });
    await t.controller.analyze();
    expect(t.encodes).toEqual([640, 592]);
    const last = t.states[t.states.length - 1];
    expect(last).toMatchObject({ phase: 'error', kind: 'invalid_output' });
    expect(t.spoken).toEqual([]);
  });

  it.each(['auth', 'network', 'timeout', 'server', 'not_ready'] as const)('does not retry or fall back on %s errors', async (kind) => {
    const t = setup({
      provider: {
        analyze: async () => {
          throw new ProviderError(kind, 'x');
        },
      },
    });
    await t.controller.analyze();
    expect(t.encodes).toEqual([640]);
    expect(t.states[t.states.length - 1]).toMatchObject({ phase: 'error', kind });
  });

  it('shows the error in the chosen language', async () => {
    const t = setup({
      language: 'zh',
      provider: {
        analyze: async () => {
          throw new ProviderError('auth', 'x');
        },
      },
    });
    await t.controller.analyze();
    const last = t.states[t.states.length - 1] as { message: string };
    expect(last.message).toContain('密钥');
  });

  it('reports a camera failure', async () => {
    const states: ControllerState[] = [];
    const controller = createAnalyzeController({
      getProvider: () => ({ id: 'local', analyze: async () => Promise.reject(new Error('never')) }),
      camera: { capture: async () => Promise.reject(new Error('no camera')) },
      encoder: { encode: async () => Promise.reject(new Error('never')) },
      speaker: { speak: async () => undefined, stop: () => undefined },
      getSettings: () => ({ language: 'en', speakResults: true }),
      onState: (s) => states.push(s),
    });
    await controller.analyze();
    expect(states[states.length - 1]).toMatchObject({ phase: 'error', kind: 'camera' });
    expect(controller.isBusy()).toBe(false);
  });

  it('ignores a second analyze while one is running', async () => {
    let release: () => void = () => undefined;
    let calls = 0;
    const t = setup({
      provider: {
        analyze: () => {
          calls += 1;
          return new Promise<ProviderResult>((resolve) => {
            release = () => resolve({ result: scene, rawText: '{}', latencyMs: 1, provider: 'remote' });
          });
        },
      },
    });
    const first = t.controller.analyze();
    await Promise.resolve();
    await t.controller.analyze();
    expect(t.controller.isBusy()).toBe(true);
    await new Promise((r) => setTimeout(r, 0));
    release();
    await first;
    expect(calls).toBe(1);
    expect(t.controller.isBusy()).toBe(false);
  });

  it('does not speak when speaking is turned off, but still reports the result', async () => {
    const t = setup({ speakResults: false });
    await t.controller.analyze();
    expect(t.spoken).toEqual([]);
    expect(t.states[t.states.length - 1].phase).toBe('done');
  });

  it('keeps the result when speech output fails', async () => {
    const states: ControllerState[] = [];
    const controller = createAnalyzeController({
      getProvider: () => ({ id: 'remote', analyze: async () => ({ result: scene, rawText: '{}', latencyMs: 1, provider: 'remote' }) }),
      camera: { capture: async () => ({ uri: 'file:///p.jpg', width: 100, height: 100 }) },
      encoder: { encode: async (photo, side) => ({ uri: photo.uri, base64: 'QQ==', width: side, height: side }) },
      speaker: { speak: async () => Promise.reject(new Error('tts down')), stop: () => undefined },
      getSettings: () => ({ language: 'en', speakResults: true }),
      onState: (s) => states.push(s),
    });
    await controller.analyze();
    expect(states[states.length - 1].phase).toBe('done');
  });

  it('repeats the last spoken text and can stop speaking', async () => {
    const t = setup();
    await t.controller.repeat();
    expect(t.spoken).toEqual([]);
    await t.controller.analyze();
    await t.controller.repeat();
    expect(t.spoken).toHaveLength(2);
    expect(t.spoken[1]).toBe(t.spoken[0]);
    const before = t.stops();
    t.controller.stopSpeaking();
    expect(t.stops()).toBe(before + 1);
  });

  it('cancels an in-flight request', async () => {
    const t = setup({
      provider: {
        analyze: (_img, ctx) =>
          new Promise<ProviderResult>((_resolve, reject) => {
            ctx.signal?.addEventListener('abort', () => reject(new ProviderError('cancelled', 'cancelled')));
          }),
      },
    });
    const pending = t.controller.analyze();
    await new Promise((r) => setTimeout(r, 0));
    t.controller.cancel();
    await pending;
    expect(t.states[t.states.length - 1]).toMatchObject({ phase: 'error', kind: 'cancelled' });
  });
});

/**
 * Live check of the app's real code path against a real llama.cpp server. Skipped unless LIVE_LLAMA_URL is set:
 *
 *   $env:LIVE_LLAMA_URL = "http://127.0.0.1:18937"; npx jest remote.live
 *
 * Uses only the public COCO images from outputs/testkit-cloud (never personal media). Writes
 * outputs/mobile-live-eval.json with every answer so they can be reviewed by eye.
 */
import * as fs from 'fs';
import * as http from 'http';
import * as path from 'path';

import { isCommandLike, isSafetyClaim } from '../../safety/guard';
import { planSpeech } from '../../safety/policy';
import type { EncodedImage, Language } from '../../core/types';
import { ProviderError } from '../../core/types';
import { createRemoteProvider } from '../remote';

const LIVE = process.env.LIVE_LLAMA_URL;
const ROOT = path.resolve(__dirname, '../../../../');
const IMAGES = path.join(ROOT, 'outputs', 'testkit-cloud', 'images');

/** Minimal fetch over node:http, so the test does not depend on the React Native fetch polyfill. */
function nodeFetch(url: string, init: RequestInit): Promise<Response> {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const request = http.request(
      { hostname: target.hostname, port: target.port, path: target.pathname, method: init.method ?? 'GET', headers: init.headers as Record<string, string> },
      (response) => {
        const chunks: Buffer[] = [];
        response.on('data', (c: Buffer) => chunks.push(c));
        response.on('end', () => {
          const body = Buffer.concat(chunks).toString('utf8');
          resolve({ status: response.statusCode ?? 0, ok: (response.statusCode ?? 0) < 300, text: async () => body } as unknown as Response);
        });
      },
    );
    request.on('error', reject);
    request.end(init.body as string | undefined);
  });
}

const CJK = /[一-鿿]/g;

interface Bucket {
  ok: number;
  invalid: number;
  errors: number;
  withheld: number;
  rawUnsafe: number;
  hazards: Record<string, number>;
  cjkShare: number[];
  ms: number[];
}
const newBucket = (): Bucket => ({ ok: 0, invalid: 0, errors: 0, withheld: 0, rawUnsafe: 0, hazards: {}, cjkShare: [], ms: [] });

(LIVE ? describe : describe.skip)('live: remote provider against a real llama-server', () => {
  it(
    'describes public images in Chinese and English with valid structured output',
    async () => {
      const files = fs
        .readdirSync(IMAGES)
        .filter((f) => f.endsWith('.jpg'))
        .sort()
        .slice(1, 13);
      expect(files).toHaveLength(12);
      const provider = createRemoteProvider({ baseUrl: LIVE as string, fetchImpl: nodeFetch as unknown as typeof fetch, timeoutMs: 120_000 });
      const rows: unknown[] = [];
      const summary: Record<Language, Bucket> = { zh: newBucket(), en: newBucket() };
      for (const language of ['zh', 'en'] as Language[]) {
        for (const file of files) {
          const base64 = fs.readFileSync(path.join(IMAGES, file)).toString('base64');
          const image: EncodedImage = { uri: `file://${file}`, base64, width: 640, height: 480 };
          const bucket = summary[language];
          try {
            const out = await provider.analyze(image, { language });
            const plan = planSpeech(out.result, language, { firstInSession: false });
            const letters = out.result.answer.replace(/\s/g, '');
            const cjk = (out.result.answer.match(CJK) ?? []).length;
            bucket.ok += 1;
            bucket.ms.push(out.latencyMs);
            bucket.cjkShare.push(letters.length ? cjk / letters.length : 0);
            bucket.hazards[out.result.hazard] = (bucket.hazards[out.result.hazard] ?? 0) + 1;
            if (plan.descriptionWithheld) bucket.withheld += 1;
            if (isCommandLike(out.result.answer) || isSafetyClaim(out.result.answer)) bucket.rawUnsafe += 1;
            rows.push({ file, language, ms: out.latencyMs, result: out.result, rawUnsafe: isCommandLike(out.result.answer) || isSafetyClaim(out.result.answer), spoken: plan.spoken });
          } catch (error) {
            const kind = error instanceof ProviderError ? error.kind : 'unknown';
            if (kind === 'invalid_output') bucket.invalid += 1;
            else bucket.errors += 1;
            rows.push({ file, language, error: kind, message: (error as Error).message });
          }
        }
      }
      fs.writeFileSync(path.join(ROOT, 'outputs', 'mobile-live-eval.json'), JSON.stringify({ summary, rows }, null, 2), 'utf8');
      console.log(JSON.stringify({ zh: { ...summary.zh, cjkShare: undefined, ms: undefined }, en: { ...summary.en, cjkShare: undefined, ms: undefined } }));
      // The provider must either return a valid result or a typed error; never garbage.
      expect(summary.zh.ok + summary.zh.invalid + summary.zh.errors).toBe(12);
      expect(summary.en.ok + summary.en.invalid + summary.en.errors).toBe(12);
      expect(summary.en.ok).toBeGreaterThan(0);
    },
    900_000,
  );
});

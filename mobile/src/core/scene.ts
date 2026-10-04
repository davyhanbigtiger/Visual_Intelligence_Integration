import { HAZARDS, ProviderError, type Hazard, type Language, type SceneResult } from './types';

/** JSON schema sent to both providers (llama.cpp converts it to a grammar, so the enum is enforced). */
export const SCENE_SCHEMA = {
  type: 'object',
  properties: {
    answer: { type: 'string' },
    hazard: { type: 'string', enum: [...HAZARDS] },
  },
  required: ['answer', 'hazard'],
  additionalProperties: false,
} as const;

/**
 * Prompts. The Chinese prompt is written in Chinese on purpose: live testing (2026-10-04, MiniCPM-V 4.6, 12 public
 * images) showed that an English prompt asking for Chinese answers produced 0% Chinese characters, while a prompt
 * written in Chinese produced ~86%. Neither prompt mentions the reader's eyesight: the model repeated it in its answers.
 * The prompts ask for observation only; what the user hears about hazards comes from fixed phrases (safety/phrases.ts).
 */
const PROMPTS: Record<Language, string> = {
  zh: [
    '请看这张摄像头画面,并返回 JSON,包含以下字段:',
    'answer:一到两句简短、客观的简体中文描述,不超过 60 个字,只描述清楚可见的环境、人物和显眼物体。不要猜测看不见的东西、身份或意图;不要给建议或命令;不要判断是否安全或危险。',
    'hazard:画面里清楚可见的危险类别:vehicle(靠近或行驶中的汽车、摩托车、公交车、自行车)、water_edge(水边)、height_drop(台阶或落差)、crowd(拥挤的人群)、animal(动物)、fire_smoke(火或烟)、obstacle(挡路的东西);都没有则 none;太暗、太模糊或只是特写、看不清则 unclear。',
  ].join('\n'),
  en: [
    'Look at this camera frame and return JSON with exactly these fields.',
    '"answer": one or two short factual sentences in English, at most 35 words, describing only what is clearly visible: the setting, any people, and prominent objects. Do not guess hidden things, identities or intentions. Do not give advice or commands, and do not say whether it is safe or dangerous.',
    '"hazard": the visible hazard category if one is clearly visible: vehicle (a car, motorcycle, bus or bicycle that appears close or moving), water_edge, height_drop (steps, stairs or a drop), crowd, animal, fire_smoke, obstacle (something blocking the way); none if nothing like that is visible; unclear if the image is too dark, blurry or close-up to tell.',
  ].join('\n'),
};

export function buildPrompt(language: Language): string {
  return PROMPTS[language];
}

function isHazard(value: unknown): value is Hazard {
  return typeof value === 'string' && (HAZARDS as readonly string[]).includes(value);
}

/** Closing characters and the opening character they pair with. */
const CLOSERS: Record<string, string> = { ')': '(', '）': '（', '}': '{', ']': '[' };

/**
 * Models sometimes end an answer with a stray closing character, such as ")" or "}" (both seen in live testing);
 * drop trailing closers that have no matching opener.
 */
function tidyAnswer(text: string): string {
  let out = text.replace(/\s+/g, ' ').trim();
  for (;;) {
    const last = out.charAt(out.length - 1);
    const opener = CLOSERS[last];
    if (!opener) return out;
    const opens = out.split(opener).length - 1;
    const closes = out.split(last).length - 1;
    if (closes <= opens) return out;
    out = out.slice(0, -1).trimEnd();
  }
}

/** Parse and validate the model output; anything malformed is an `invalid_output` error, never a guess. */
export function parseSceneResult(text: string): SceneResult {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new ProviderError('invalid_output', 'The model did not return valid JSON.');
  }
  if (typeof data !== 'object' || data === null) {
    throw new ProviderError('invalid_output', 'The model output is not a JSON object.');
  }
  const record = data as Record<string, unknown>;
  const answer = typeof record.answer === 'string' ? tidyAnswer(record.answer) : '';
  if (!answer) throw new ProviderError('invalid_output', 'The model output has no answer.');
  if (!isHazard(record.hazard)) {
    throw new ProviderError('invalid_output', 'The model output has an unknown hazard value.');
  }
  return { answer: answer.slice(0, 600), hazard: record.hazard };
}

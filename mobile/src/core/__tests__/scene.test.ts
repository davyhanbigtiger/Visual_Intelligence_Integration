import { buildPrompt, parseSceneResult, SCENE_SCHEMA } from '../scene';
import { HAZARDS, ProviderError } from '../types';

const valid = { answer: 'A bear on grass.', hazard: 'animal' };

describe('parseSceneResult', () => {
  it('parses a valid result', () => {
    expect(parseSceneResult(JSON.stringify(valid))).toEqual({ answer: 'A bear on grass.', hazard: 'animal' });
  });

  it('ignores extra fields a model might add', () => {
    expect(parseSceneResult(JSON.stringify({ ...valid, scene: 'nature', hazard_confidence: 'high' }))).toEqual({
      answer: 'A bear on grass.',
      hazard: 'animal',
    });
  });

  it.each([
    ['not json', 'garbage 12 34'],
    ['truncated json', '{"answer": "cut off'],
    ['json array', '[1,2]'],
    ['json null', 'null'],
    ['empty answer', JSON.stringify({ ...valid, answer: '   ' })],
    ['missing answer', JSON.stringify({ hazard: 'none' })],
    ['missing hazard', JSON.stringify({ answer: 'x' })],
    ['unknown hazard', JSON.stringify({ ...valid, hazard: 'ghost' })],
    ['coordinate garbage', '{"answer": "tennis court100 211 998 989'],
  ])('rejects %s as invalid_output', (_name, text) => {
    expect(() => parseSceneResult(text)).toThrow(ProviderError);
    try {
      parseSceneResult(text);
    } catch (error) {
      expect((error as ProviderError).kind).toBe('invalid_output');
    }
  });

  it('drops a stray unbalanced closing bracket the models sometimes add', () => {
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: 'A person on a beach.)' })).answer).toBe('A person on a beach.');
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: 'A person (left) on a beach.' })).answer).toBe('A person (left) on a beach.');
  });

  it('drops stray trailing braces and brackets too (a real answer ended with "。}")', () => {
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: '一群人在网球场上。}' })).answer).toBe('一群人在网球场上。');
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: 'Players on a court.]' })).answer).toBe('Players on a court.');
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: 'A list [of items]' })).answer).toBe('A list [of items]');
  });

  it('collapses whitespace and caps absurdly long answers', () => {
    const long = 'word '.repeat(500);
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: ' a \n b ' })).answer).toBe('a b');
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: long })).answer.length).toBeLessThanOrEqual(600);
  });
});

describe('SCENE_SCHEMA and buildPrompt', () => {
  it('lists exactly the hazard enum the parser accepts, and nothing else', () => {
    expect(SCENE_SCHEMA.properties.hazard.enum).toEqual([...HAZARDS]);
    expect(SCENE_SCHEMA.required).toEqual(['answer', 'hazard']);
    expect(SCENE_SCHEMA.additionalProperties).toBe(false);
    expect(Object.keys(SCENE_SCHEMA.properties)).toEqual(['answer', 'hazard']);
  });

  it('writes the Chinese prompt in Chinese (an English prompt asking for Chinese returned English in live tests)', () => {
    const zh = buildPrompt('zh');
    expect((zh.match(/[一-鿿]/g) ?? []).length).toBeGreaterThan(80);
    expect(zh).toContain('简体中文');
    expect(buildPrompt('en')).toContain('in English');
  });

  it('forbids advice and safety judgments, and never mentions the reader’s eyesight (the model repeated it)', () => {
    expect(buildPrompt('en')).toMatch(/do not say whether it is safe or dangerous/i);
    expect(buildPrompt('zh')).toContain('不要判断是否安全或危险');
    for (const lang of ['zh', 'en'] as const) {
      expect(buildPrompt(lang)).not.toMatch(/limited sight|visually impaired|blind|视力|盲人|视障/i);
    }
  });
});

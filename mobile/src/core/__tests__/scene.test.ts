import { buildPrompt, parseSceneResult, SCENE_SCHEMA } from '../scene';
import { CONFIDENCES, HAZARDS, ProviderError, SCENES } from '../types';

const valid = { answer: 'A bear on grass.', scene: 'nature', hazard: 'animal', hazard_confidence: 'high' };

describe('parseSceneResult', () => {
  it('parses a valid result', () => {
    expect(parseSceneResult(JSON.stringify(valid))).toEqual({
      answer: 'A bear on grass.',
      scene: 'nature',
      hazard: 'animal',
      hazardConfidence: 'high',
    });
  });

  it('defaults a missing or unknown confidence to low (never to high)', () => {
    const { hazard_confidence: _drop, ...rest } = valid;
    expect(parseSceneResult(JSON.stringify(rest)).hazardConfidence).toBe('low');
    expect(parseSceneResult(JSON.stringify({ ...valid, hazard_confidence: 'certain' })).hazardConfidence).toBe('low');
  });

  it.each([
    ['not json', 'garbage 12 34'],
    ['truncated json', '{"answer": "cut off'],
    ['json array', '[1,2]'],
    ['json null', 'null'],
    ['empty answer', JSON.stringify({ ...valid, answer: '   ' })],
    ['missing answer', JSON.stringify({ scene: 'nature', hazard: 'none' })],
    ['unknown scene', JSON.stringify({ ...valid, scene: 'moon' })],
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
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: 'A person (left) on a beach.' })).answer).toBe(
      'A person (left) on a beach.',
    );
  });

  it('collapses whitespace and caps absurdly long answers', () => {
    const long = 'word '.repeat(500);
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: ' a \n b ' })).answer).toBe('a b');
    expect(parseSceneResult(JSON.stringify({ ...valid, answer: long })).answer.length).toBeLessThanOrEqual(600);
  });
});

describe('SCENE_SCHEMA and buildPrompt', () => {
  it('lists exactly the enums the parser accepts', () => {
    expect(SCENE_SCHEMA.properties.scene.enum).toEqual([...SCENES]);
    expect(SCENE_SCHEMA.properties.hazard.enum).toEqual([...HAZARDS]);
    expect(SCENE_SCHEMA.properties.hazard_confidence.enum).toEqual([...CONFIDENCES]);
    expect(SCENE_SCHEMA.required).toEqual(['answer', 'scene', 'hazard', 'hazard_confidence']);
    expect(SCENE_SCHEMA.additionalProperties).toBe(false);
  });

  it('asks for the right language and forbids advice and safety judgments', () => {
    expect(buildPrompt('zh')).toContain('Simplified Chinese');
    expect(buildPrompt('en')).toContain('in English');
    for (const lang of ['zh', 'en'] as const) {
      expect(buildPrompt(lang)).toMatch(/Do not give advice, commands or safety judgments/);
    }
  });
});

import type { SceneResult } from '../../core/types';
import { guardDescription, isCommandLike } from '../guard';
import { PHRASES } from '../phrases';
import { planSpeech } from '../policy';

const base: SceneResult = { answer: 'A road with parked cars.', scene: 'road', hazard: 'none', hazardConfidence: 'high' };

describe('isCommandLike', () => {
  it.each([
    'Go left.',
    'Turn right now',
    'Walk straight ahead',
    'You must stop',
    'A car is near. Stop immediately.',
    "Don't cross here",
    'Run away from the water',
    'Keep away from the edge',
    'Consider crossing now',
    '请向左走',
    '不要过马路',
    '赶紧离开这里',
    '快跑',
    '前面有车。小心!',
    '往左走',
  ])('flags command-like text: %s', (text) => {
    expect(isCommandLike(text)).toBe(true);
  });

  it.each([
    'A person walks along a road with cars parked nearby.',
    'Two people are running on the beach.',
    'The sign says stop.',
    '一个人在街上走路,旁边停着几辆车。',
    '海边有人在跑步。',
    '跑步的人从左边经过。',
    '',
  ])('does not flag descriptive text: %s', (text) => {
    expect(isCommandLike(text)).toBe(false);
  });
});

describe('guardDescription', () => {
  it('returns trimmed descriptive text and withholds commands and empty text', () => {
    expect(guardDescription('  A quiet street.  ')).toBe('A quiet street.');
    expect(guardDescription('Go left.')).toBeNull();
    expect(guardDescription('   ')).toBeNull();
  });
});

describe('fixed phrases', () => {
  const all = (lang: 'zh' | 'en') => {
    const p = PHRASES[lang];
    return [...Object.values(p.hazard), ...Object.values(p.scene), p.unclear, p.uncertainHazard, p.noHazardNote, p.disclaimer, p.withheld];
  };

  it.each(['zh', 'en'] as const)('none of the %s phrases is command-like', (lang) => {
    for (const phrase of all(lang)) expect(isCommandLike(phrase)).toBe(false);
  });

  it.each(['zh', 'en'] as const)('no %s hazard or scene phrase claims safety or tells the user to run', (lang) => {
    const p = PHRASES[lang];
    for (const phrase of [...Object.values(p.hazard), ...Object.values(p.scene)]) {
      expect(phrase).not.toMatch(/safe|安全|\brun\b|跑|逃/i);
    }
  });

  it('only mentions safety in the no-hazard note, and there only to deny it', () => {
    expect(PHRASES.zh.noHazardNote).toContain('不代表安全');
    expect(PHRASES.en.noHazardNote).toContain('does not mean it is safe');
  });

  it('has a phrase for every hazard category in both languages', () => {
    const zh = Object.keys(PHRASES.zh.hazard).sort();
    expect(Object.keys(PHRASES.en.hazard).sort()).toEqual(zh);
    expect(zh).toEqual(['animal', 'crowd', 'fire_smoke', 'height_drop', 'obstacle', 'vehicle', 'water_edge']);
  });
});

describe('planSpeech', () => {
  it('speaks a confident hazard alert before the description', () => {
    const plan = planSpeech({ ...base, hazard: 'vehicle' }, 'zh', { firstInSession: false });
    expect(plan.alert).toBe(PHRASES.zh.hazard.vehicle);
    expect(plan.spoken[0]).toBe(PHRASES.zh.hazard.vehicle);
    expect(plan.spoken[1]).toBe('A road with parked cars.');
    expect(plan.sceneLine).toBeNull();
  });

  it('does not alert on a low-confidence hazard, and says it is unsure instead', () => {
    const plan = planSpeech({ ...base, hazard: 'water_edge', hazardConfidence: 'low' }, 'en', { firstInSession: false });
    expect(plan.alert).toBeNull();
    expect(plan.uncertainty).toBe(PHRASES.en.uncertainHazard);
    expect(plan.noHazardNote).toBeNull();
  });

  it('says it cannot judge when the image is unclear and never reassures', () => {
    const plan = planSpeech({ ...base, hazard: 'unclear', hazardConfidence: 'high' }, 'zh', { firstInSession: false });
    expect(plan.uncertainty).toBe(PHRASES.zh.unclear);
    expect(plan.noHazardNote).toBeNull();
    expect(plan.spoken.join(' ')).not.toMatch(/安全/);
  });

  it('adds a friendly scene line only when there is no alert or uncertainty', () => {
    const beach = planSpeech({ ...base, scene: 'beach' }, 'en', { firstInSession: false });
    expect(beach.sceneLine).toBe(PHRASES.en.scene.beach);
    const beachWithHazard = planSpeech({ ...base, scene: 'beach', hazard: 'water_edge' }, 'en', { firstInSession: false });
    expect(beachWithHazard.sceneLine).toBeNull();
  });

  it('shows (does not speak) a no-hazard note that never says "safe"', () => {
    const plan = planSpeech({ ...base, scene: 'other' }, 'en', { firstInSession: false });
    expect(plan.noHazardNote).toBe(PHRASES.en.noHazardNote);
    expect(plan.spoken).toEqual(['A road with parked cars.']);
  });

  it('withholds a command-like description and speaks the fixed notice instead', () => {
    const plan = planSpeech({ ...base, answer: 'Go left now.' }, 'en', { firstInSession: false });
    expect(plan.descriptionWithheld).toBe(true);
    expect(plan.spoken.join(' ')).not.toContain('Go left');
    expect(plan.spoken).toContain(PHRASES.en.withheld);
  });

  it('appends the disclaimer last, only on the first analysis of a session', () => {
    const first = planSpeech(base, 'zh', { firstInSession: true });
    expect(first.spoken[first.spoken.length - 1]).toBe(PHRASES.zh.disclaimer);
    const later = planSpeech(base, 'zh', { firstInSession: false });
    expect(later.disclaimer).toBeNull();
  });
});

import type { SceneResult } from '../../core/types';
import { guardDescription, isCommandLike, isSafetyClaim } from '../guard';
import { PHRASES } from '../phrases';
import { planSpeech } from '../policy';

const base: SceneResult = { answer: 'A road with parked cars.', hazard: 'none' };

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
    '人物很多，需小心',
    '当心台阶',
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

describe('isSafetyClaim', () => {
  it.each([
    '环境安全。',
    '没有可见危险或障碍。',
    '无危险。',
    '可以放心。',
    'It looks safe here.',
    'There is no danger.',
    'Nothing dangerous is visible.',
    'The path is harmless.',
    'No obstacles ahead.',
  ])('flags safety assertions: %s', (text) => {
    expect(isSafetyClaim(text)).toBe(true);
  });

  it.each(['A bear on the grass.', '有熊和草地。', 'A kitchen with a refrigerator and a stove.', '路边停着一辆卡车。'])(
    'does not flag plain descriptions: %s',
    (text) => {
      expect(isSafetyClaim(text)).toBe(false);
    },
  );
});

describe('guardDescription', () => {
  it('returns trimmed descriptive text and withholds commands and empty text', () => {
    expect(guardDescription('  A quiet street.  ')).toBe('A quiet street.');
    expect(guardDescription('Go left.')).toBeNull();
    expect(guardDescription('   ')).toBeNull();
  });

  it('keeps the useful sentences and drops only the unsafe ones (real model output, 2026-10-04)', () => {
    expect(guardDescription('环境清晰，有熊和草地。没有可见危险或障碍。')).toBe('环境清晰，有熊和草地。');
    expect(guardDescription('环境为室内，有毛绒玩具。物体清晰可见，无危险。视力强，环境安全。清晰可见的物体和空间。')).toBe(
      '环境为室内，有毛绒玩具。清晰可见的物体和空间。',
    );
    expect(guardDescription('The scene shows a tennis court. It is safe. Players are visible.')).toBe(
      'The scene shows a tennis court. Players are visible.',
    );
  });

  it('drops sentences that leak the prompt about eyesight', () => {
    expect(guardDescription('环境是户外网球场，人物众多。视力可能不佳，需小心。')).toBe('环境是户外网球场，人物众多。');
    expect(guardDescription('A park. For a visually impaired person it is open.')).toBe('A park.');
  });

  it('withholds everything when every sentence is unsafe', () => {
    expect(guardDescription('环境安全。无危险。')).toBeNull();
    expect(guardDescription('Go left. It is safe.')).toBeNull();
  });
});

describe('fixed phrases', () => {
  const all = (lang: 'zh' | 'en') => {
    const p = PHRASES[lang];
    return [...Object.values(p.hazard), p.unclear, p.disclaimer, p.withheld];
  };

  it.each(['zh', 'en'] as const)('none of the %s phrases is command-like', (lang) => {
    for (const phrase of all(lang)) expect(isCommandLike(phrase)).toBe(false);
  });

  it.each(['zh', 'en'] as const)('no %s hazard phrase claims safety or tells the user to run', (lang) => {
    for (const phrase of Object.values(PHRASES[lang].hazard)) {
      expect(phrase).not.toMatch(/safe|安全|\brun\b|跑|逃/i);
    }
  });

  it('tells the user that hazard alerts are experimental and that silence is not a safety signal', () => {
    expect(PHRASES.zh.disclaimer).toContain('实验性');
    expect(PHRASES.zh.disclaimer).toContain('没有提示不代表没有危险');
    expect(PHRASES.en.disclaimer).toContain('experimental');
    expect(PHRASES.en.disclaimer).toContain('no alert does not mean there is no danger');
  });

  it('has a phrase for every actionable hazard category in both languages', () => {
    const zh = Object.keys(PHRASES.zh.hazard).sort();
    expect(Object.keys(PHRASES.en.hazard).sort()).toEqual(zh);
    expect(zh).toEqual(['animal', 'crowd', 'fire_smoke', 'height_drop', 'obstacle', 'vehicle', 'water_edge']);
  });
});

describe('planSpeech', () => {
  it('speaks a hazard alert before the description', () => {
    const plan = planSpeech({ ...base, hazard: 'vehicle' }, 'zh', { firstInSession: false });
    expect(plan.alert).toBe(PHRASES.zh.hazard.vehicle);
    expect(plan.spoken[0]).toBe(PHRASES.zh.hazard.vehicle);
    expect(plan.spoken[1]).toBe('A road with parked cars.');
  });

  it('says it cannot judge when the image is unclear', () => {
    const plan = planSpeech({ ...base, hazard: 'unclear' }, 'zh', { firstInSession: false });
    expect(plan.uncertainty).toBe(PHRASES.zh.unclear);
    expect(plan.alert).toBeNull();
  });

  it('never reassures when no hazard is reported: only the description is spoken', () => {
    const plan = planSpeech(base, 'en', { firstInSession: false });
    expect(plan.alert).toBeNull();
    expect(plan.uncertainty).toBeNull();
    expect(plan.spoken).toEqual(['A road with parked cars.']);
    expect(plan.spoken.join(' ')).not.toMatch(/safe|danger/i);
  });

  it('strips an unsafe sentence from the description but keeps the rest', () => {
    const plan = planSpeech({ answer: '有熊和草地。环境安全。', hazard: 'none' }, 'zh', { firstInSession: false });
    expect(plan.spoken).toEqual(['有熊和草地。']);
    expect(plan.descriptionWithheld).toBe(false);
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

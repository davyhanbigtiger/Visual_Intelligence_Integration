import { normalizeUtterance, parseCommand } from '../commands';

describe('parseCommand', () => {
  it.each([
    ['放大', 'zoom_in'],
    ['再放大一点', 'zoom_in'],
    ['拉近', 'zoom_in'],
    ['缩小', 'zoom_out'],
    ['拉远一点', 'zoom_out'],
    ['还原', 'zoom_reset'],
    ['恢复默认', 'zoom_reset'],
    ['看看周围', 'analyze'],
    ['前面有什么', 'analyze'],
    ['这是什么', 'analyze'],
    ['重复一遍', 'repeat'],
    ['再说一次', 'repeat'],
    ['停止', 'stop'],
    ['别说了', 'stop'],
    ['安静', 'stop'],
    ['zoom in', 'zoom_in'],
    ['Zoom in!', 'zoom_in'],
    ['get closer', 'zoom_in'],
    ['zoom out please', 'zoom_out'],
    ['reset zoom', 'zoom_reset'],
    ['no zoom', 'zoom_reset'],
    ['what do you see', 'analyze'],
    ["what's in front", 'analyze'],
    ['describe the scene', 'analyze'],
    ['repeat that', 'repeat'],
    ['say that again', 'repeat'],
    ['stop', 'stop'],
    ['be quiet', 'stop'],
  ])('%s -> %s', (text, type) => {
    expect(parseCommand(text).type).toBe(type);
  });

  it('switches language', () => {
    expect(parseCommand('切换到英文')).toEqual({ type: 'language', language: 'en' });
    expect(parseCommand('说中文')).toEqual({ type: 'language', language: 'zh' });
    expect(parseCommand('switch to English')).toEqual({ type: 'language', language: 'en' });
    expect(parseCommand('speak Chinese')).toEqual({ type: 'language', language: 'zh' });
  });

  it.each(['不要放大', '别缩小', "don't zoom in", 'do not describe', '你好', 'hello', '', '   ', '。。。'])(
    'ignores negations and unrelated speech: %j',
    (text) => {
      expect(parseCommand(text).type).toBe('unknown');
    },
  );

  it('keeps the original text on unknown commands for the "heard" line', () => {
    expect(parseCommand('哈哈 好的')).toEqual({ type: 'unknown', text: '哈哈 好的' });
  });

  it('prefers stop over everything else, even inside negations', () => {
    expect(parseCommand('stop zooming')).toEqual({ type: 'stop' });
    expect(parseCommand('不要说了')).toEqual({ type: 'stop' });
  });
});

describe('normalizeUtterance', () => {
  it('lowercases, strips punctuation, keeps apostrophes, collapses spaces', () => {
    expect(normalizeUtterance("  Don't   ZOOM, in!! ")).toBe("don't zoom in");
    expect(normalizeUtterance('放大。')).toBe('放大');
  });
});

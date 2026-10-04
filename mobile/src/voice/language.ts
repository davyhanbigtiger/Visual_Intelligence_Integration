import type { Language } from '../core/types';

/** BCP-47 tags used for both speech recognition and speech synthesis. */
export const SPEECH_LOCALE: Record<Language, string> = { zh: 'zh-CN', en: 'en-US' };

/** Words the recognizer should favour; improves accuracy for the short command vocabulary. */
export const COMMAND_HINTS: Record<Language, string[]> = {
  zh: ['看看周围', '描述一下', '这是什么', '放大', '缩小', '还原', '重复', '停止', '切换到英文', '切换到中文'],
  en: ['look around', 'describe', 'what do you see', 'zoom in', 'zoom out', 'reset zoom', 'repeat', 'stop', 'switch to Chinese'],
};

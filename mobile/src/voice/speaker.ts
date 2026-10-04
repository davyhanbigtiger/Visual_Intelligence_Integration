import * as Speech from 'expo-speech';

import type { SpeakerPort } from '../controller/analyze';
import { SPEECH_LOCALE } from './language';
import { splitForSpeech } from './speechChunks';

/** System text-to-speech (AVSpeechSynthesizer on iOS). Free and offline; voices depend on what the device has installed. */
export function createSpeaker(): SpeakerPort {
  let token = 0;
  return {
    async speak(text, language) {
      const mine = (token += 1);
      for (const chunk of splitForSpeech(text, Speech.maxSpeechInputLength)) {
        if (mine !== token) return;
        await new Promise<void>((resolve) => {
          Speech.speak(chunk, {
            language: SPEECH_LOCALE[language],
            rate: 1.0,
            onDone: () => resolve(),
            onStopped: () => resolve(),
            onError: () => resolve(),
          });
        });
      }
    },
    stop() {
      token += 1;
      void Speech.stop();
    },
  };
}

import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';

import type { ImageEncoderPort } from '../controller/analyze';
import { computeResize } from './resize';

/**
 * Re-encode a captured photo as JPEG (quality 0.8) with the longest side at most `maxSide`.
 * 640 px keeps the on-device model in its cheap single/low-slice range and keeps the upload around 50 KB.
 */
export function createImageEncoder(): ImageEncoderPort {
  return {
    async encode(photo, maxSide) {
      let context = ImageManipulator.manipulate(photo.uri);
      const resize = computeResize(photo.width, photo.height, maxSide);
      if (resize) context = context.resize(resize);
      const image = await context.renderAsync();
      const saved = await image.saveAsync({ format: SaveFormat.JPEG, compress: 0.8, base64: true });
      if (!saved.base64) throw new Error('Image encoding returned no data.');
      return { uri: saved.uri, base64: saved.base64, width: saved.width, height: saved.height };
    },
  };
}

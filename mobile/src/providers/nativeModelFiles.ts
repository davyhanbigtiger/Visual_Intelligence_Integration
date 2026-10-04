import { Directory, File, Paths } from 'expo-file-system';

import type { ModelFilesPort } from './localModel';

/**
 * Stored in the app cache directory on purpose: it is excluded from iCloud / device backups, so a 1.26 GB model does
 * not eat the user's backup quota. The trade-off is that the OS may remove it under storage pressure; the status
 * check then reports "missing" and the user can download it again.
 */
const directory = new Directory(Paths.cache, 'models');

function fileFor(name: string): File {
  return new File(directory, name);
}

export const nativeModelFiles: ModelFilesPort = {
  size(name) {
    const file = fileFor(name);
    return file.exists ? file.size : null;
  },
  path(name) {
    return fileFor(name).uri;
  },
  remove(name) {
    const file = fileFor(name);
    if (file.exists) file.delete();
  },
  async download(spec, onProgress, signal) {
    directory.create({ intermediates: true, idempotent: true });
    const task = File.createDownloadTask(spec.url, fileFor(spec.name));
    const subscription = task.addListener('progress', (p) => onProgress(p.bytesWritten, p.totalBytes));
    const onAbort = () => task.cancel();
    signal?.addEventListener('abort', onAbort, { once: true });
    try {
      await task.downloadAsync();
    } finally {
      signal?.removeEventListener('abort', onAbort);
      subscription.remove();
      task.release();
    }
  },
};

/**
 * The on-device model: MiniCPM-V 4.6 (Q4_K_M) plus its Q8_0 vision projector, from the public ggml-org repository.
 * Sizes are the byte counts of the files we verified server-side (see scripts/cloud/setup_server.sh); on the phone
 * we can only check the size, not a SHA-256 (hashing >1 GB in JS is impractical).
 */
export interface ModelFileSpec {
  name: string;
  url: string;
  bytes: number;
}

const BASE = 'https://huggingface.co/ggml-org/MiniCPM-V-4.6-GGUF/resolve/main';

export const LOCAL_MODEL: { main: ModelFileSpec; mmproj: ModelFileSpec } = {
  main: { name: 'MiniCPM-V-4.6-Q4_K_M.gguf', url: `${BASE}/MiniCPM-V-4.6-Q4_K_M.gguf`, bytes: 529_101_536 },
  mmproj: { name: 'mmproj-MiniCPM-V-4.6-Q8_0.gguf', url: `${BASE}/mmproj-MiniCPM-V-4.6-Q8_0.gguf`, bytes: 727_954_528 },
};

export type FileState = 'missing' | 'partial' | 'ready';

export function fileState(actualBytes: number | null, spec: ModelFileSpec): FileState {
  if (actualBytes === null || actualBytes <= 0) return 'missing';
  return actualBytes === spec.bytes ? 'ready' : 'partial';
}

export interface ModelFilesPort {
  /** Size in bytes, or null when the file does not exist. */
  size(name: string): number | null;
  path(name: string): string;
  remove(name: string): void;
  download(spec: ModelFileSpec, onProgress: (bytesWritten: number, totalBytes: number) => void, signal?: AbortSignal): Promise<void>;
}

export interface ModelStatus {
  main: FileState;
  mmproj: FileState;
  ready: boolean;
  totalBytes: number;
}

export function modelStatus(files: Pick<ModelFilesPort, 'size'>): ModelStatus {
  const main = fileState(files.size(LOCAL_MODEL.main.name), LOCAL_MODEL.main);
  const mmproj = fileState(files.size(LOCAL_MODEL.mmproj.name), LOCAL_MODEL.mmproj);
  return { main, mmproj, ready: main === 'ready' && mmproj === 'ready', totalBytes: LOCAL_MODEL.main.bytes + LOCAL_MODEL.mmproj.bytes };
}

/**
 * Download whatever is missing, one file at a time. A partial file is removed and fetched again from the start.
 * After each download the size must match exactly, otherwise the file is removed and the call fails.
 */
export async function downloadModel(
  files: ModelFilesPort,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<void> {
  const specs = [LOCAL_MODEL.main, LOCAL_MODEL.mmproj];
  const total = specs.reduce((sum, s) => sum + s.bytes, 0);
  let done = 0;
  for (const spec of specs) {
    const state = fileState(files.size(spec.name), spec);
    if (state === 'ready') {
      done += spec.bytes;
      onProgress(done / total);
      continue;
    }
    if (state === 'partial') files.remove(spec.name);
    await files.download(spec, (written) => onProgress((done + Math.min(written, spec.bytes)) / total), signal);
    if (fileState(files.size(spec.name), spec) !== 'ready') {
      files.remove(spec.name);
      throw new Error(`Downloaded file ${spec.name} has the wrong size.`);
    }
    done += spec.bytes;
    onProgress(done / total);
  }
}

export type DeviceFit = 'ok' | 'tight' | 'too_small' | 'unknown';

/**
 * Rough, unmeasured guess: the model files are ~1.26 GB and inference needs more on top, so phones with less than
 * ~6 GB RAM may be killed by the OS for memory. These thresholds are estimates, not test results.
 */
export function deviceFit(totalMemoryBytes: number | null): DeviceFit {
  if (totalMemoryBytes === null || !(totalMemoryBytes > 0)) return 'unknown';
  if (totalMemoryBytes < 3.5e9) return 'too_small';
  if (totalMemoryBytes < 5.5e9) return 'tight';
  return 'ok';
}

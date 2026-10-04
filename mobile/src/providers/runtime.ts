import { createLlamaRnPort } from './llamaRnPort';
import { createLocalProvider } from './local';
import { LOCAL_MODEL, modelStatus } from './localModel';
import { nativeModelFiles } from './nativeModelFiles';

/** One on-device provider for the whole app, so the model is loaded at most once. */
export const localProvider = createLocalProvider(
  createLlamaRnPort({
    model: nativeModelFiles.path(LOCAL_MODEL.main.name),
    mmproj: nativeModelFiles.path(LOCAL_MODEL.mmproj.name),
  }),
  () => modelStatus(nativeModelFiles).ready,
);

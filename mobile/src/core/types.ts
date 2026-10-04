export type Language = 'zh' | 'en';

export const HAZARDS = [
  'none',
  'vehicle',
  'water_edge',
  'height_drop',
  'crowd',
  'animal',
  'fire_smoke',
  'obstacle',
  'unclear',
] as const;
export type Hazard = (typeof HAZARDS)[number];

/**
 * What the model returns. The model only describes and flags a hazard category; fixed phrases decide what is spoken.
 * Scene labels and a confidence field were removed after live testing (2026-10-04): on 12 public images the scene
 * label was wrong in about half the cases and the confidence was always "low", so neither carried information.
 */
export interface SceneResult {
  answer: string;
  hazard: Hazard;
}

export interface EncodedImage {
  uri: string;
  /** Raw base64, without a data: prefix. */
  base64: string;
  width: number;
  height: number;
}

export type ProviderId = 'local' | 'remote';

export interface AnalyzeContext {
  language: Language;
  signal?: AbortSignal;
}

export interface ProviderResult {
  result: SceneResult;
  rawText: string;
  latencyMs: number;
  provider: ProviderId;
}

export interface VisionProvider {
  readonly id: ProviderId;
  analyze(image: EncodedImage, ctx: AnalyzeContext): Promise<ProviderResult>;
}

export type ProviderErrorKind =
  | 'network'
  | 'timeout'
  | 'auth'
  | 'server'
  | 'invalid_output'
  | 'not_ready'
  | 'not_configured'
  | 'too_slow'
  | 'cancelled';

export class ProviderError extends Error {
  readonly kind: ProviderErrorKind;
  readonly status?: number;

  constructor(kind: ProviderErrorKind, message: string, status?: number) {
    super(message);
    this.name = 'ProviderError';
    this.kind = kind;
    this.status = status;
    Object.setPrototypeOf(this, ProviderError.prototype);
  }
}

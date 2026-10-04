export type Language = 'zh' | 'en';

export const SCENES = ['road', 'beach', 'indoor', 'nature', 'crowd', 'other', 'unclear'] as const;
export type Scene = (typeof SCENES)[number];

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

export const CONFIDENCES = ['low', 'medium', 'high'] as const;
export type Confidence = (typeof CONFIDENCES)[number];

/** What the model returns. The model only describes and classifies; fixed phrases decide what is spoken. */
export interface SceneResult {
  answer: string;
  scene: Scene;
  hazard: Hazard;
  hazardConfidence: Confidence;
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

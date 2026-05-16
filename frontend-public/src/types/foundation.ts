export interface Foundation {
  readonly name: string;
  readonly scope: string;
  readonly url: string;
  readonly city: string | null;
  readonly country: string | null;
  readonly services: readonly string[];
  readonly diseases: readonly string[];
}

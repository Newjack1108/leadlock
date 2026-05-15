import { CONFIGURATOR_FRONT_FACES, type ConfiguratorFrontFace } from '@/lib/types';

/** Allowed manual front faces for non-square standard configurator products (short edges only). */
export function getAllowedConfiguratorFrontFaces(
  widthValue: string,
  lengthValue: string
): ConfiguratorFrontFace[] {
  const width = Number(widthValue);
  const length = Number(lengthValue);
  if (!Number.isFinite(width) || !Number.isFinite(length) || width <= 0 || length <= 0 || width === length) {
    return [...CONFIGURATOR_FRONT_FACES];
  }
  return width > length ? ['left', 'right'] : ['top', 'bottom'];
}

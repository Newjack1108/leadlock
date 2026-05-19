import { CONFIGURATOR_FRONT_FACES, type ConfiguratorFrontFace } from '@/lib/types';

/** Allowed front faces for standard configurator products (any edge of the footprint). */
export function getAllowedConfiguratorFrontFaces(
  _widthValue: string,
  _lengthValue: string
): ConfiguratorFrontFace[] {
  return [...CONFIGURATOR_FRONT_FACES];
}

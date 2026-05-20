/** Google Maps directions URL (factory → customer). */
export function googleMapsDirectionsUrl(origin: string, destination: string): string {
  const params = new URLSearchParams({
    api: '1',
    origin: origin.trim(),
    destination: destination.trim(),
  });
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

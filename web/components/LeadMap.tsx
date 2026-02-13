'use client';

import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet';
import L from 'leaflet';
import type { LeadLocationItem } from '@/lib/types';
import 'leaflet/dist/leaflet.css';

// Fix default marker icon in Next.js (webpack doesn't resolve leaflet's default icon paths)
const DefaultIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
L.Marker.prototype.options.icon = DefaultIcon;

interface LeadMapProps {
  locations: LeadLocationItem[];
  loading?: boolean;
}

export default function LeadMap({ locations, loading = false }: LeadMapProps) {
  if (loading) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-lg border border-border bg-muted/30">
        <p className="text-sm text-muted-foreground">Loading map...</p>
      </div>
    );
  }

  if (!locations || locations.length === 0) {
    return (
      <div className="flex h-[300px] flex-col items-center justify-center gap-1 rounded-lg border border-border bg-muted/30 px-4 text-center">
        <p className="text-sm text-muted-foreground">
          No leads with postcodes in this period
        </p>
        <p className="text-xs text-muted-foreground">
          Add postcodes to leads or customers to see them on the map. Try &quot;All&quot; for all-time.
        </p>
      </div>
    );
  }

  return (
    <div className="h-[300px] w-full overflow-hidden rounded-lg">
      <MapContainer
        center={[54.5, -2.5]}
        zoom={6}
        scrollWheelZoom={false}
        className="h-full w-full"
        attributionControl={false}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {locations.map((loc, i) => (
          <Marker key={`${loc.postcode}-${i}`} position={[loc.lat, loc.lng]}>
            <Popup>
              <span className="font-medium">{loc.postcode}</span>
              <br />
              <span className="text-muted-foreground">
                {loc.count} lead{loc.count !== 1 ? 's' : ''}
              </span>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}

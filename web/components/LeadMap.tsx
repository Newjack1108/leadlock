'use client';

import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet';
import type { LeadLocationItem } from '@/lib/types';
import 'leaflet/dist/leaflet.css';

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
          <CircleMarker
            key={`${loc.postcode}-${i}`}
            center={[loc.lat, loc.lng]}
            radius={6}
            pathOptions={{
              fillColor: '#22c55e',
              color: '#16a34a',
              weight: 1,
              fillOpacity: 1,
              opacity: 1,
            }}
          >
            <Popup>
              <span className="font-medium">{loc.postcode}</span>
              <br />
              <span className="text-muted-foreground">
                {loc.count} lead{loc.count !== 1 ? 's' : ''}
              </span>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  );
}

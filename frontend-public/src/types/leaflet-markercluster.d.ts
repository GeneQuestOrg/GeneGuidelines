import "leaflet";

declare module "leaflet" {
  function markerClusterGroup(options?: {
    maxClusterRadius?: number;
    chunkedLoading?: boolean;
  }): import("leaflet").LayerGroup;
}

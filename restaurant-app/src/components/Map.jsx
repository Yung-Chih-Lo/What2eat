// src/components/Map.jsx
import React from 'react';
import { GoogleMap, useLoadScript, Marker, InfoWindow } from '@react-google-maps/api';

const libraries = ['places'];
const mapContainerStyle = {
  width: '100%',
  height: '400px',
};
const options = {
  disableDefaultUI: true,
  zoomControl: true,
};

const Map = ({ location, restaurants }) => {
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: import.meta.env.GOOGLE_MAPS_API_KEY,
    libraries,
  });

  // console.log('Google Maps API Key:', import.meta.env.GOOGLE_MAPS_API_KEY);

  const [selected, setSelected] = React.useState(null);

  if (loadError) return <div>Error loading maps</div>;
  if (!isLoaded) return <div>Loading Maps</div>;

  return (
    <GoogleMap
      mapContainerStyle={mapContainerStyle} 
      zoom={14}
      center={location} // 使用 location 作为中心点
      options={options}
    >
      {restaurants.map((restaurant) => (
        <Marker
          key={restaurant.id}
          position={{ lat: restaurant.lat, lng: restaurant.lng }}
          onClick={() => {
            setSelected(restaurant);
          }}
        />
      ))}

      {selected ? (
        <InfoWindow
          position={{ lat: selected.lat, lng: selected.lng }}
          onCloseClick={() => {
            setSelected(null);
          }}
        >
          <div className="text-black">
            <h2 className="font-bold">{selected.name}</h2>
            <p>{selected.address}</p>
          </div>
        </InfoWindow>
      ) : null}
    </GoogleMap>
  );
};

export default Map;

// src/utils/fetchRestaurants.js
export const fetchNearbyRestaurants = async (location, radius = 1500) => {
    const { lat, lng } = location;
    const url = `http://localhost:5001/api/nearby-restaurants?lat=${lat}&lng=${lng}&radius=${radius}`;
  
    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error('Network response was not ok');
      }
      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching restaurants:', error);
      return [];
    }
  };
  
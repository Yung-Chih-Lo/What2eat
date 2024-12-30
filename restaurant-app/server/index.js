// server/index.js

// TODO 將 server 改成由 python 執行

const express = require('express');
const axios = require('axios');
const cors = require('cors');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5001; // mac port 5000不能用所以改5001

app.use(cors());

app.get('/api/nearby-restaurants', async (req, res) => {
  const { lat, lng, radius } = req.query;

  if (!lat || !lng) {
    return res.status(400).json({ error: 'Missing latitude or longitude' });
  }

  const apiKey = process.env.GOOGLE_MAPS_API_KEY;
  const url = `https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=${lat},${lng}&radius=${radius || 1500}&type=restaurant&key=${apiKey}`;

  try {
    const response = await axios.get(url);
    const data = response.data;

    if (data.status !== 'OK') {
      throw new Error(`Google Places API error: ${data.status}`);
    }

    const results = data.results.map((place) => ({
      id: place.place_id,
      name: place.name,
      address: place.vicinity,
      lat: place.geometry.location.lat,
      lng: place.geometry.location.lng,
      distance: calculateDistance(
        { lat: parseFloat(lat), lng: parseFloat(lng) },
        { lat: place.geometry.location.lat, lng: place.geometry.location.lng }
      ),
    }));

    res.json(results);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Failed to fetch restaurants' });
  }
});

const calculateDistance = (loc1, loc2) => {
  const toRad = (value) => (value * Math.PI) / 180;
  const R = 6371e3; // 地球半徑
  const φ1 = toRad(loc1.lat);
  const φ2 = toRad(loc2.lat);
  const Δφ = toRad(loc2.lat - loc1.lat);
  const Δλ = toRad(loc2.lng - loc1.lng);

  const a =
    Math.sin(Δφ / 2) * Math.sin(Δφ / 2) +
    Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  const distance = R * c;
  return Math.round(distance);
};

app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

import React, { useState } from 'react';
import { MapPin, Loader } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Modal from 'react-modal';
import { fetchNearbyRestaurants } from '../utils/fetchRestaurants';
import Map from './Map';

// 設置 Modal 的根元素，確保在應用中只設置一次
Modal.setAppElement('#root');

const NearbySearch = () => {
  const navigate = useNavigate(); // 初始化 useNavigate
  const [location, setLocation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [nearbyRestaurants, setNearbyRestaurants] = useState([]);

  // 獲取當前位置
  const getCurrentLocation = () => {
    setIsLoading(true);
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        async (position) => {
          const userLocation = {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          };
          setLocation(userLocation);

          const restaurants = await fetchNearbyRestaurants(userLocation);
          setNearbyRestaurants(restaurants);
          setIsLoading(false);
        },
        (error) => {
          console.error('定位錯誤：', error);
          setIsLoading(false);
        }
      );
    } else {
      console.error('Geolocation is not supported by this browser.');
      setIsLoading(false);
    }
  };

  // 處理導航到 Restaurant 頁面
  const handleNavigateToRestaurant = (restaurantName) => {
    navigate(`/restaurant/${encodeURIComponent(restaurantName)}`);
  };

  return (
    <div className="max-w-4xl mx-auto">
      <div className="bg-gray-800/50 backdrop-blur-sm rounded-lg shadow-lg p-6 mb-6 border border-gray-700">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-2xl font-bold text-white">探索附近美食</h2>
          <button
            onClick={getCurrentLocation}
            className="flex items-center gap-2 bg-emerald-500 text-white px-4 py-2 rounded-lg hover:bg-emerald-600 transition-all duration-200 shadow-lg shadow-emerald-500/50"
          >
            <MapPin size={20} />
            {isLoading ? '定位中...' : '取得目前位置'}
          </button>
        </div>

        {isLoading && (
          <div className="flex justify-center items-center py-8 text-white">
            <Loader className="animate-spin" size={24} />
            <span className="ml-2">搜尋附近餐廳中...</span>
          </div>
        )}

        {location && (
          <div className="mb-4">
            <div className="bg-gray-700/50 p-4 rounded-lg border border-gray-600">
              <p className="text-gray-300">
                目前位置：{location.lat.toFixed(6)}, {location.lng.toFixed(6)}
              </p>
            </div>
          </div>
        )}

        {location && (
          <div className="mb-6">
            {/* 假設您有一個 Map 組件 */}
            <Map location={location} restaurants={nearbyRestaurants} />
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {nearbyRestaurants.map((restaurant) => (
            <div
              key={restaurant.id}
              className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 shadow-lg backdrop-blur-sm hover:bg-gray-700/50 transition-all duration-200"
            >
              <h3 className="font-bold text-lg mb-2 text-white">{restaurant.name}</h3>
              <p className="text-gray-400 text-sm mb-2">{restaurant.address}</p>
              <div className="flex items-center text-gray-400 text-sm mb-2">
                <MapPin size={16} className="mr-1" />
                <span>{restaurant.distance} 公尺</span>
              </div>
              <button
                onClick={() => handleNavigateToRestaurant(restaurant.name)}
                className="mt-2 bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600 transition-all duration-200"
              >
                獲取評論
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default NearbySearch;

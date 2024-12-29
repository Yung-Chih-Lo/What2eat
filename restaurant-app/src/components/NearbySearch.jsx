// src/components/NearbySearch.jsx
import React, { useState } from 'react';
import { MapPin, Loader } from 'lucide-react';
import Map from './Map';
import { fetchNearbyRestaurants } from '../utils/fetchRestaurants';
import Modal from 'react-modal';

const NearbySearch = () => {
  const [location, setLocation] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [nearbyRestaurants, setNearbyRestaurants] = useState([]);
  
  // 新增状态来存储评论
  const [reviews, setReviews] = useState({});
  const [isReviewLoading, setIsReviewLoading] = useState({});
  const [reviewErrors, setReviewErrors] = useState({});

  const [selectedRestaurant, setSelectedRestaurant] = useState(null);
  const [modalReviews, setModalReviews] = useState([]);
  const [modalError, setModalError] = useState(null);
  const [isModalLoading, setIsModalLoading] = useState(false);

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

  const startScraping = async (keyword) => {
    try {
      const response = await fetch('http://localhost:5001/api/scrape-reviews', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ keyword }),
      });
      
      if (!response.ok) {
        throw new Error('爬蟲請求失敗');
      }
      
      return await response.json();
    } catch (error) {
      console.error('爬蟲錯誤:', error);
      throw error;
    }
  };

  // 處理獲取評論的函數
  const handleGetReviews = async (restaurantName) => {
    
    setIsReviewLoading(prev => ({ ...prev, [restaurantName]: true }));
    setReviewErrors(prev => ({ ...prev, [restaurantName]: null }));

    try {
      const data = await startScraping(restaurantName);
      setReviews(prev => ({ ...prev, [restaurantName]: data.reviews }));
    } catch (error) {
      setReviewErrors(prev => ({ ...prev, [restaurantName]: '獲取評論失敗' }));
    } finally {
      setIsReviewLoading(prev => ({ ...prev, [restaurantName]: false }));
    }
  };


  const handleOpenModal = async (restaurantName) => {
    setSelectedRestaurant(restaurantName);
    setIsModalLoading(true);
    setModalError(null);
    setModalReviews([]);

    try {
      const data = await startScraping(restaurantName);
      setModalReviews(data.reviews);
    } catch (error) {
      setModalError('獲取評論失敗');
    } finally {
      setIsModalLoading(false);
    }
  };

  const handleCloseModal = () => {
    setSelectedRestaurant(null);
    setModalReviews([]);
    setModalError(null);
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
                onClick={() => handleGetReviews(restaurant.name)}
                className="mt-2 bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600 transition-all duration-200"
                disabled={isReviewLoading[restaurant.name]}
              >
                {isReviewLoading[restaurant.name] ? '獲取中...' : '獲取評論'}
              </button>
              
              {reviews[restaurant.name] && (
                <div className="mt-4 p-2 bg-gray-700/50 rounded">
                  <h4 className="text-white font-semibold mb-2">評論</h4>
                  {reviews[restaurant.name].length > 0 ? (
                    <ul className="list-disc list-inside text-gray-200">
                      {reviews[restaurant.name].map((review, index) => (
                        <li key={index}>{review}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-gray-400">暫無評論</p>
                  )}
                </div>
              )}
              {reviewErrors[restaurant.name] && (
                <p className="mt-2 text-red-500">{reviewErrors[restaurant.name]}</p>
              )}
            </div>
          ))}
        </div>
      </div>
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
              onClick={() => handleOpenModal(restaurant.name)}
              className="mt-2 bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600 transition-all duration-200"
            >
              獲取評論
            </button>
          </div>
        ))}
      </div>

      <Modal
        isOpen={!!selectedRestaurant}
        onRequestClose={handleCloseModal}
        contentLabel="Restaurant Reviews"
        className="max-w-2xl mx-auto mt-20 bg-white p-6 rounded-lg shadow-lg outline-none"
        overlayClassName="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-start z-50"
      >
        <button onClick={handleCloseModal} className="text-red-500 font-bold float-right">×</button>
        <h2 className="text-2xl font-bold mb-4">評論{selectedRestaurant}</h2>
        {isModalLoading && <Loader className="animate-spin" size={24} />}
        {modalError && <p className="text-red-500">{modalError}</p>}
        {modalReviews.length > 0 ? (
          <ul className="list-disc list-inside">
            {modalReviews.map((review, index) => (
              <li key={index}>{review}</li>
            ))}
          </ul>
        ) : (
          !isModalLoading && <p>暫無評論</p>
        )}
      </Modal>
    </div>
  );
};

export default NearbySearch;

import React from 'react';
import { Routes, Route, Link, useLocation, Navigate } from 'react-router-dom';
import RestaurantSearch from './components/RestaurantSearch';
import NearbySearch from './components/NearbySearch';
import { Search, MapPin } from 'lucide-react';

function App() {
  const location = useLocation(); // 獲取當前路徑

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-4 bg-fixed">
      {/* 背景紋理 */}
      <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI1IiBoZWlnaHQ9IjUiPgo8cmVjdCB3aWR0aD0iNSIgaGVpZ2h0PSI1IiBmaWxsPSIjMDAwMDAwMjAiPjwvcmVjdD4KPHBhdGggZD0iTTAgNUw1IDBaTTYgNEw0IDZaTS0xIDFMMSAtMVoiIHN0cm9rZT0iIzAwMDAwMDQwIiBvcGFjaXR5PSIwLjUiPjwvcGF0aD4KPC9zdmc+')] opacity-20"></div>
      
      <div className="relative">
        {/* 頂部標題和導航按鈕 */}
        <div className="flex flex-col sm:flex-row justify-between items-center mb-6 text-white">
          <h1 className="text-4xl font-bold mb-4 sm:mb-0 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400">
            What2eat
          </h1>
          <div className="flex gap-4">
            <Link
              to="/review"
              className={`flex items-center px-4 py-2 rounded-lg transition-all duration-200 ${
                location.pathname === '/review'
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/50'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Search className="mr-2" size={20} />
              搜尋評價
            </Link>
            <Link
              to="/nearby"
              className={`flex items-center px-4 py-2 rounded-lg transition-all duration-200 ${
                location.pathname === '/nearby'
                  ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/50'
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <MapPin className="mr-2" size={20} />
              探索附近
            </Link>
          </div>
        </div>

        {/* 配置路由 */}
        <Routes>
          {/* 重定向 / 到 /review */}
          <Route path="/" element={<Navigate to="/review" replace />} />
          <Route path="/review" element={<RestaurantSearch />} />
          <Route path="/nearby" element={<NearbySearch />} />
          <Route path="/restaurant/:name" element={<RestaurantSearch />} />
        </Routes>
      </div>
    </div>
  );
}

export default App;

import React, { useState, useEffect } from 'react';
import { Search, Star, MapPin, Clock, Phone, AlertCircle, MessageCircle, FolderInput, ChevronDown, ChevronUp } from 'lucide-react';
import HourglassSpinner from './HourglassSpinner';

const RestaurantSearch = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResult, setSearchResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reviewData, setReviewData] = useState(null);
  const [scrapingStatus, setScrapingStatus] = useState(null);
  const [analysisData, setAnalysisData] = useState(null);
  const [showAnalysis, setShowAnalysis] = useState(false);

  // 檢查爬蟲狀態
  const checkScrapingStatus = async (keyword) => {
    try {
      const response = await fetch(`http://localhost:5000/api/reviews/${encodeURIComponent(keyword)}/status`);
      if (response.ok) {
        const status = await response.json();
        setScrapingStatus(status);
        return status;
      }
      return null;
    } catch (error) {
      console.error('檢查爬蟲狀態失敗:', error);
      return null;
    }
  };

  // 開始爬蟲
  const startScraping = async (keyword) => {
    try {
      const response = await fetch('http://localhost:5000/api/scrape-reviews', {
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

  // 檢查爬蟲結果
  const checkReviewResults = async (keyword) => {
    try {
      const response = await fetch(`http://localhost:5000/api/reviews/${keyword}`);
      if (response.ok) {
        const data = await response.json();
        
        // 檢查分析檔案是否存在
        const analysisResponse = await fetch(`http://localhost:5000/api/reviews/${keyword}_analysis.json`);
        if (analysisResponse.ok) {
          const analysisData = await analysisResponse.json();
          setAnalysisData(analysisData);
        }
        
        return data;
      }
      return null;
    } catch (error) {
      console.error('檢查結果錯誤:', error);
      return null;
    }
  };

  // 處理搜尋
  const handleSearch = async (e) => {
    e.preventDefault();
    if (searchTerm.trim()) {
      setIsLoading(true);
      setError(null);
      setSearchResult(null);
      setReviewData(null);
      setScrapingStatus(null);
      setAnalysisData(null);
      
      try {
        await startScraping(searchTerm);
        
        let statusCheckInterval;
        const startTime = Date.now();
        const timeoutDuration = 600000; // 10分鐘超時
        
        statusCheckInterval = setInterval(async () => {
          const status = await checkScrapingStatus(searchTerm);
          
          if (status) {
            if (status.status === 'completed') {
              clearInterval(statusCheckInterval);
              const results = await checkReviewResults(searchTerm);
              if (results) {
                setReviewData(results);
                setSearchResult({
                  name: searchTerm,
                  rating: calculateAverageRating(results),
                  reviewCount: results.length,
                  updatedTime: new Date().toLocaleString(),
                  source: "Google Maps"
                });
                setIsLoading(false);
              }
            } else if (status.status === 'error') {
              clearInterval(statusCheckInterval);
              setError(status.error || '爬蟲過程發生錯誤');
              setIsLoading(false);
            }
          }
          
          if (Date.now() - startTime > timeoutDuration) {
            clearInterval(statusCheckInterval);
            setError('搜尋超時，請稍後再試');
            setIsLoading(false);
          }
        }, 3000);
        
      } catch (error) {
        setError(error.message);
        setIsLoading(false);
      }
    }
  };

  // 計算平均評分
  const calculateAverageRating = (reviews) => {
    if (!reviews || reviews.length === 0) return 0;
    const totalRating = reviews.reduce((sum, review) => {
      const rating = parseFloat(review.評分.split(' ')[0]);
      return sum + (isNaN(rating) ? 0 : rating);
    }, 0);
    return (totalRating / reviews.length).toFixed(1);
  };

  return (
    <div className="w-full max-w-3xl mx-auto pt-12">
      {/* 標題區 */}
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-white mb-3 tracking-wide">
          美食
          <span className="text-blue-500">T</span>
          <span className="text-red-500">r</span>
          <span className="text-yellow-500">u</span>
          <span className="text-green-500">e</span>
          <span className="text-blue-500">G</span>
          <span className="text-green-500">L</span>
          <span className="text-red-500">E</span> Map
        </h1>
        <p className="text-gray-400 text-lg">
          探索最真實的美食地圖，篩選最真誠的餐廳體驗
        </p>
      </div>
      
      {/* 搜尋區域 */}
      <div className="bg-white/10 backdrop-blur-lg p-8 rounded-2xl shadow-2xl mb-8 border border-white/20">
        <form onSubmit={handleSearch} className="relative">
          <div className="relative flex items-center">
            <input
              type="text"
              placeholder="搜尋餐廳名稱..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full px-6 py-4 pr-36 rounded-xl 
                       bg-white/80 backdrop-blur-sm
                       border-2 border-transparent
                       focus:outline-none focus:border-gray-400
                       text-gray-700 placeholder-gray-400
                       text-lg transition-all duration-300
                       shadow-inner"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading}
              className={`absolute right-2 px-6 py-3 
                       bg-gradient-to-r from-gray-600 to-gray-700
                       text-white rounded-lg
                       hover:from-gray-700 hover:to-gray-800
                       transition-all duration-300 
                       flex items-center gap-2 
                       shadow-lg shadow-gray-500/30
                       ${isLoading ? 'opacity-75 cursor-not-allowed' : ''}`}
            >
              {isLoading ? (
                <>
                  <HourglassSpinner size={20} />
                  <span className="font-medium">搜尋中</span>
                </>
              ) : (
                <>
                  <Search size={20} />
                  <span className="font-medium">搜尋</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* 錯誤提示 */}
      {error && (
        <div className="bg-red-500/10 backdrop-blur-lg rounded-2xl p-4 mb-8 border border-red-500/20">
          <div className="flex items-center gap-2 text-red-400">
            <AlertCircle size={20} />
            <p>{error}</p>
          </div>
        </div>
      )}

      {/* 載入中狀態 */}
      {isLoading && (
        <div className="bg-white/10 backdrop-blur-lg rounded-2xl p-8 shadow-2xl border border-white/20">
          <div className="flex flex-col items-center gap-4">
            <HourglassSpinner size={48} />
            <p className="text-gray-300 text-lg">正在分析餐廳評論...</p>
            {scrapingStatus && (
              <p className="text-gray-400">
                已收集 {scrapingStatus.total_reviews} 則評論
              </p>
            )}
          </div>
        </div>
      )}

      {/* 搜尋結果 */}
      {!isLoading && searchResult && (
        <div className="space-y-6">
          {/* 基本資訊卡片 */}
          <div className="bg-white/10 backdrop-blur-lg rounded-2xl overflow-hidden shadow-2xl border border-white/20">
            <div className="p-8">
              <div className="flex justify-between items-start mb-6">
                <div>
                  <h3 className="text-2xl font-bold text-white mb-2">
                    {searchResult.name}
                  </h3>
                </div>
                <div className="flex items-center gap-1 bg-gray-500/20 px-4 py-2 rounded-full">
                  <Star className="text-yellow-400" size={24} />
                  <span className="text-white font-semibold">
                    {searchResult.rating}
                  </span>
                </div>
              </div>
              
              <div className="space-y-4">
                <div className="flex items-center gap-3 text-gray-300">
                  <MessageCircle size={18} className="text-gray-400" />
                  <span>評論數量: {searchResult.reviewCount}</span>
                </div>
                <div className="flex items-center gap-3 text-gray-300">
                  <Clock size={18} className="text-gray-400" />
                  <span>資料更新時間: {searchResult.updatedTime}</span>
                </div>
                <div className="flex items-center gap-3 text-gray-300">
                  <FolderInput size={18} className="text-gray-400" />
                  <span>資料來源: {searchResult.source}</span>
                </div>
              </div>
            </div>
            
            {/* AI 分析摘要 */}
            {analysisData && (
              <div className="border-t border-white/10 p-8">
                <div className="mb-4">
                  <h4 className="text-lg font-semibold text-white">AI 分析摘要</h4>
                </div>
                <p className="text-gray-300 leading-relaxed">
                  {analysisData.summary}
                </p>
                <button
                  onClick={() => setShowAnalysis(!showAnalysis)}
                  className="mt-4 flex items-center gap-2 text-gray-400 hover:text-white transition-colors duration-200"
                >
                  {showAnalysis ? (
                    <>
                      <ChevronUp size={20} />
                      <span>隱藏詳細分析</span>
                    </>
                  ) : (
                    <>
                      <ChevronDown size={20} />
                      <span>查看詳細分析</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>

          {/* 展開的詳細分析 */}
          {showAnalysis && analysisData && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl overflow-hidden shadow-2xl border border-white/20">
              <div className="p-8">
                <h4 className="text-lg font-semibold text-white mb-6">餐廳優缺點分析</h4>
                <div className="space-y-6">
                  {/* 優點 */}
                  <div>
                    <h5 className="text-green-400 font-medium mb-2">主要優點</h5>
                    <ul className="list-disc list-inside space-y-2">
                      {analysisData.individual_analysis.positives
                        .filter(item => item.length > 5)
                        .slice(0, 5)
                        .map((point, index) => (
                          <li key={index} className="text-gray-300">{point}</li>
                        ))}
                    </ul>
                  </div>
                  
                  {/* 缺點 */}
                  <div>
                    <h5 className="text-red-400 font-medium mb-2">主要缺點</h5>
                    <ul className="list-disc list-inside space-y-2">
                      {analysisData.individual_analysis.negatives
                        .filter(item => item.length > 5)
                        .slice(0, 5)
                        .map((point, index) => (
                          <li key={index} className="text-gray-300">{point}</li>
                        ))}
                    </ul>
                  </div>
                  
                  {/* 推薦項目 */}
                  <div>
                    <h5 className="text-yellow-400 font-medium mb-2">推薦必點</h5>
                    <ul className="list-disc list-inside space-y-2">
                      {analysisData.individual_analysis.recommendations
                        .filter(item => item.length > 5)
                        .slice(0, 5)
                        .map((point, index) => (
                          <li key={index} className="text-gray-300">{point}</li>
                        ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          )}


          {/* 評論列表 */}
          {reviewData && (
            <div className="bg-white/10 backdrop-blur-lg rounded-2xl overflow-hidden shadow-2xl border border-white/20">
              <div className="p-8">
                <h4 className="text-lg font-semibold text-white mb-4">最新評論</h4>
                <div className="space-y-4">
                  {reviewData.slice(0, 5).map((review, index) => (
                    <div 
                      key={index}
                      className="bg-white/5 rounded-xl p-4 border border-white/10 animate-slide-down"
                      style={{ animationDelay: `${index * 0.1}s` }}
                    >
                      <div className="flex items-center gap-2 mb-2">
                        <Star className="text-yellow-400" size={16} />
                        <span className="text-white">{review.評分}</span>
                        <span className="text-gray-400 text-sm">
                          · {review.評論時間}
                        </span>
                      </div>
                      <p className="text-gray-300 text-sm">{review.評論}</p>
                      <p className="text-gray-400 text-xs mt-2">- {review.用戶}</p>
                    </div>
                  ))}
                </div>
              </div>
              
              
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RestaurantSearch;
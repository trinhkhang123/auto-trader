import React, { useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { useTrades } from '../context/TradeContext';
import { format } from 'date-fns';
import { ArrowLeftIcon, ArrowUpIcon, ArrowDownIcon } from '@heroicons/react/20/solid';

export default function TradeDetail() {
  const { id } = useParams();
  const { fetchTradeDetail, cancelOrder } = useTrades();
  const [trade, setTrade] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  // Lấy thông tin chi tiết giao dịch
  useEffect(() => {
    const loadTrade = async () => {
      try {
        setLoading(true);
        const data = await fetchTradeDetail(id);
        setTrade(data);
        setError(null);
      } catch (err) {
        console.error('Lỗi khi tải chi tiết giao dịch:', err);
        setError('Không thể tải thông tin giao dịch');
      } finally {
        setLoading(false);
      }
    };

    loadTrade();
  }, [id, fetchTradeDetail]);

  // Xử lý huỷ lệnh
  const handleCancelOrder = async () => {
    if (window.confirm('Bạn có chắc chắn muốn huỷ lệnh này không?')) {
      const result = await cancelOrder(id);
      if (result.success) {
        // Quay lại trang trước đó sau khi huỷ thành công
        navigate(-1);
      } else {
        alert(result.error || 'Có lỗi xảy ra khi huỷ lệnh');
      }
    }
  };

  // Hiển thị loading
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  // Hiển thị lỗi
  if (error || !trade) {
    return (
      <div className="bg-red-50 border-l-4 border-red-400 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">{error || 'Không tìm thấy thông tin giao dịch'}</p>
          </div>
        </div>
        <div className="mt-4">
          <Link to="/" className="text-primary-600 hover:text-primary-900 font-medium">
            &larr; Quay lại danh sách giao dịch
          </Link>
        </div>
      </div>
    );
  }

  // Tính toán các thông số
  const isLong = trade.side === 'buy';
  const isOpen = trade.status === 'open';
  const profitPercent = trade.profit_percent ? parseFloat(trade.profit_percent).toFixed(2) : 0;
  const isProfit = parseFloat(profitPercent) > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="md:flex md:items-center md:justify-between">
        <div className="flex-1 min-w-0">
          <Link 
            to="/" 
            className="inline-flex items-center text-sm font-medium text-gray-500 hover:text-gray-700"
          >
            <ArrowLeftIcon className="h-4 w-4 mr-1" />
            Quay lại
          </Link>
          <h2 className="mt-2 text-2xl font-bold leading-7 text-gray-900 sm:text-3xl sm:truncate">
            {trade.asset} - {isLong ? 'Mua' : 'Bán'} {trade.quantity} {trade.asset.split('USDT')[0]}
          </h2>
          <div className="mt-1 flex flex-col sm:flex-row sm:flex-wrap sm:mt-0 sm:space-x-6">
            <div className="mt-2 flex items-center text-sm text-gray-500">
              <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                isOpen 
                  ? 'bg-blue-100 text-blue-800' 
                  : trade.status === 'closed' 
                    ? 'bg-purple-100 text-purple-800'
                    : 'bg-gray-100 text-gray-800'
              }`}>
                {isOpen ? 'Đang mở' : trade.status === 'closed' ? 'Đã đóng' : 'Đã huỷ'}
              </span>
              <span className="ml-2">
                {format(new Date(trade.timestamp), 'dd/MM/yyyy HH:mm:ss')}
              </span>
            </div>
            <div className="mt-2 flex items-center text-sm text-gray-500">
              <span>Bot: </span>
              <span className="ml-1 font-medium text-gray-900">{trade.bot || 'N/A'}</span>
            </div>
          </div>
        </div>
        {isOpen && (
          <div className="mt-4 flex md:mt-0 md:ml-4">
            <button
              type="button"
              onClick={handleCancelOrder}
              className="ml-3 inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
            >
              Huỷ lệnh
            </button>
          </div>
        )}
      </div>

      {/* Thông tin chính */}
      <div className="bg-white shadow overflow-hidden sm:rounded-lg">
        <div className="px-4 py-5 sm:px-6 bg-gray-50">
          <h3 className="text-lg leading-6 font-medium text-gray-900">Thông tin giao dịch</h3>
        </div>
        <div className="border-t border-gray-200">
          <dl>
            <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Tổng quan</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-3 bg-gray-50 rounded-md">
                    <p className="text-xs font-medium text-gray-500">Lợi nhuận</p>
                    <p className={`text-xl font-semibold ${isProfit ? 'text-green-600' : 'text-red-600'}`}>
                      {profitPercent}%
                    </p>
                  </div>
                  <div className="p-3 bg-gray-50 rounded-md">
                    <p className="text-xs font-medium text-gray-500">Giá vào</p>
                    <p className="text-lg font-semibold">{parseFloat(trade.entry_price).toFixed(2)}</p>
                  </div>
                  <div className="p-3 bg-gray-50 rounded-md">
                    <p className="text-xs font-medium text-gray-500">Giá hiện tại</p>
                    <p className="text-lg font-semibold">
                      {trade.current_price ? parseFloat(trade.current_price).toFixed(2) : 'N/A'}
                    </p>
                  </div>
                </div>
              </dd>
            </div>
            <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Thông tin lệnh</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="font-medium">Loại lệnh</p>
                    <p className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      isLong ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                    }`}>
                      {isLong ? 'Mua' : 'Bán'} {trade.type || 'Market'}
                    </p>
                  </div>
                  <div>
                    <p className="font-medium">Khối lượng</p>
                    <p>{parseFloat(trade.quantity).toFixed(4)} {trade.asset.split('USDT')[0]}</p>
                  </div>
                  <div>
                    <p className="font-medium">Đòn bẩy</p>
                    <p>{trade.leverage || 1}x</p>
                  </div>
                  <div>
                    <p className="font-medium">Giá trị</p>
                    <p>${(parseFloat(trade.entry_price) * parseFloat(trade.quantity)).toFixed(2)}</p>
                  </div>
                </div>
              </dd>
            </div>
            
            {/* Take Profit và Stop Loss */}
            <div className="bg-gray-50 px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Take Profit / Stop Loss</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="font-medium flex items-center">
                      <ArrowUpIcon className="h-4 w-4 text-green-500 mr-1" />
                      Take Profit
                    </p>
                    {trade.take_profit && trade.take_profit.length > 0 ? (
                      <ul className="mt-1 space-y-1">
                        {trade.take_profit.map((tp, index) => (
                          <li key={index} className="flex justify-between">
                            <span>TP{index + 1}: {parseFloat(tp.price).toFixed(2)}</span>
                            <span className={`${tp.hit ? 'text-green-600 font-medium' : ''}`}>
                              {tp.hit ? 'Đã chạm' : 'Chờ'}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-gray-500">Không có</p>
                    )}
                  </div>
                  <div>
                    <p className="font-medium flex items-center">
                      <ArrowDownIcon className="h-4 w-4 text-red-500 mr-1" />
                      Stop Loss
                    </p>
                    {trade.stop_loss ? (
                      <div className="mt-1">
                        <p>{parseFloat(trade.stop_loss).toFixed(2)}</p>
                        {trade.stop_loss_hit && (
                          <span className="text-red-600 text-sm font-medium">Đã chạm</span>
                        )}
                      </div>
                    ) : (
                      <p className="text-gray-500">Không có</p>
                    )}
                  </div>
                </div>
              </dd>
            </div>

            {/* Thông tin bổ sung */}
            <div className="bg-white px-4 py-5 sm:grid sm:grid-cols-3 sm:gap-4 sm:px-6">
              <dt className="text-sm font-medium text-gray-500">Thông tin bổ sung</dt>
              <dd className="mt-1 text-sm text-gray-900 sm:mt-0 sm:col-span-2">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="font-medium">ID giao dịch</p>
                    <p className="font-mono text-sm">{trade.id}</p>
                  </div>
                  <div>
                    <p className="font-medium">Thời gian tạo</p>
                    <p>{format(new Date(trade.timestamp), 'dd/MM/yyyy HH:mm:ss')}</p>
                  </div>
                  {trade.closed_at && (
                    <div>
                      <p className="font-medium">Thời gian đóng</p>
                      <p>{format(new Date(trade.closed_at), 'dd/MM/yyyy HH:mm:ss')}</p>
                    </div>
                  )}
                  <div>
                    <p className="font-medium">Ghi chú</p>
                    <p>{trade.notes || 'Không có'}</p>
                  </div>
                </div>
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </div>
  );
}

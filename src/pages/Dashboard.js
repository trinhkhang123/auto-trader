import React, { useState } from 'react';
import { useTrades } from '../context/TradeContext';
import { useNavigate } from 'react-router-dom';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { ArrowDownIcon, ArrowUpIcon, ArrowsUpDownIcon } from '@heroicons/react/20/solid';

// Định dạng số tiền
const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', {
    style: 'decimal',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
};

export default function Dashboard() {
  const { 
    trades, 
    loading, 
    error, 
    filters, 
    setFilters, 
    cancelOrder, 
    balance 
  } = useTrades();
  
  const navigate = useNavigate();
  const [sortConfig, setSortConfig] = useState({ key: 'timestamp', direction: 'desc' });

  // Xử lý sắp xếp
  const requestSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  // Sắp xếp danh sách giao dịch
  const sortedTrades = React.useMemo(() => {
    const sortableTrades = [...trades];
    if (sortConfig.key) {
      sortableTrades.sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
          return sortConfig.direction === 'asc' ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
          return sortConfig.direction === 'asc' ? 1 : -1;
        }
        return 0;
      });
    }
    return sortableTrades;
  }, [trades, sortConfig]);

  // Hiển thị loading
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary-500"></div>
      </div>
    );
  }

  // Hiển thị lỗi
  if (error) {
    return (
      <div className="bg-red-50 border-l-4 border-red-400 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg className="h-5 w-5 text-red-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
            </svg>
          </div>
          <div className="ml-3">
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Thông tin số dư */}
        <div className="bg-white shadow rounded-lg p-4 mb-6">
          <h2 className="text-lg font-medium text-gray-900 mb-4">Thông tin tài khoản</h2>
          {balance.loading ? (
            <div className="animate-pulse flex space-x-4">
              <div className="h-4 bg-gray-200 rounded w-1/4"></div>
            </div>
          ) : balance.error ? (
            <div className="text-red-500">{balance.error}</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-blue-50 p-3 rounded-lg">
                <p className="text-sm text-gray-500">Số dư khả dụng</p>
                <p className="text-xl font-semibold text-blue-700">${formatCurrency(balance.available)}</p>
              </div>
              <div className="bg-green-50 p-3 rounded-lg">
                <p className="text-sm text-gray-500">Tổng tài sản</p>
                <p className="text-xl font-semibold text-green-700">${formatCurrency(balance.equity)}</p>
              </div>
              <div className="bg-yellow-50 p-3 rounded-lg">
                <p className="text-sm text-gray-500">Ký quỹ đã dùng</p>
                <p className="text-xl font-semibold text-yellow-700">${formatCurrency(balance.used_margin)}</p>
              </div>
              <div className="bg-purple-50 p-3 rounded-lg">
                <p className="text-sm text-gray-500">Số dư ví</p>
                <p className="text-xl font-semibold text-purple-700">${formatCurrency(balance.wallet_balance)}</p>
              </div>
            </div>
          )}
        </div>

        {/* Bộ lọc và bảng giao dịch */}
        <div className="bg-white shadow overflow-hidden sm:rounded-lg">
          {/* Bộ lọc */}
          <div className="px-4 py-5 sm:px-6 bg-gray-50 border-b border-gray-200">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="w-full sm:w-1/3">
                <label htmlFor="status" className="block text-sm font-medium text-gray-700">Trạng thái</label>
                <select
                  id="status"
                  className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm rounded-md"
                  value={filters.status}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value })}
                >
                  <option value="ALL">Tất cả</option>
                  <option value="OPEN">Đang mở</option>
                  <option value="CLOSED">Đã đóng</option>
                  <option value="CANCELLED">Đã huỷ</option>
                </select>
              </div>
              <div className="w-full sm:w-1/3">
                <label htmlFor="symbol" className="block text-sm font-medium text-gray-700">Mã</label>
                <input
                  type="text"
                  id="symbol"
                  className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                  placeholder="Ví dụ: BTCUSDT"
                  value={filters.symbol}
                  onChange={(e) => setFilters({ ...filters, symbol: e.target.value })}
                />
              </div>
              <div className="w-full sm:w-1/3">
                <label htmlFor="bot" className="block text-sm font-medium text-gray-700">Bot</label>
                <input
                  type="text"
                  id="bot"
                  className="mt-1 block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 focus:outline-none focus:ring-primary-500 focus:border-primary-500 sm:text-sm"
                  placeholder="Tên bot"
                  value={filters.bot}
                  onChange={(e) => setFilters({ ...filters, bot: e.target.value })}
                />
              </div>
            </div>
          </div>

          {/* Bảng giao dịch */}
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th 
                    scope="col" 
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer"
                    onClick={() => requestSort('timestamp')}
                  >
                    <div className="flex items-center">
                      Thời gian
                      {sortConfig.key === 'timestamp' ? (
                        sortConfig.direction === 'asc' ? 
                          <ArrowUpIcon className="ml-1 h-4 w-4" /> : 
                          <ArrowDownIcon className="ml-1 h-4 w-4" />
                      ) : (
                        <ArrowsUpDownIcon className="ml-1 h-4 w-4 text-gray-400" />
                      )}
                    </div>
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Cặp giao dịch
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Loại lệnh
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Giá vào
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Giá hiện tại
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Stop loss
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Take profit
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Lợi nhuận
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Leverage
                  </th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Trạng thái
                  </th>
                  <th scope="col" className="relative px-6 py-3">
                    <span className="sr-only">Hành động</span>
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {sortedTrades.length > 0 ? (
                  sortedTrades.map((trade) => (
                    <tr key={trade.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.created_at ? format(new Date(trade.created_at), 'dd/MM/yyyy HH:mm') : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">{trade.symbol}</div>
                        <div className="text-sm text-gray-500">{trade.bot || 'N/A'}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          trade.side === 'Buy' 
                            ? 'bg-green-100 text-green-800' 
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {trade.side === 'Buy' ? 'Mua' : 'Bán'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {parseFloat(trade.entry_price).toFixed(2)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.current_price ? parseFloat(trade.current_price).toFixed(2) : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.stop_loss ? parseFloat(trade.stop_loss).toFixed(2) : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.take_profit ? parseFloat(trade.take_profit).toFixed(2) : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        {trade.pnl !== undefined ? (
                          <span className={`font-medium ${
                            parseFloat(trade.pnl) > 0 
                              ? 'text-green-600' 
                              : parseFloat(trade.pnl) < 0 
                                ? 'text-red-600' 
                                : 'text-gray-600'
                          }`}>
                            {parseFloat(trade.pnl).toFixed(2)}%
                          </span>
                        ) : 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {trade.leverage}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${
                          trade.status === 'OPEN' 
                            ? 'bg-blue-100 text-blue-800' 
                            : trade.status === 'CLOSED' 
                              ? 'bg-purple-100 text-purple-800'
                              : trade.status === 'FILLED'
                                ? 'bg-green-100 text-green-800'
                                : 'bg-gray-100 text-gray-800'
                        }`}>
                          {trade.status === 'OPEN' 
                            ? 'Đang mở' 
                            : trade.status === 'CLOSED' 
                              ? 'Đã đóng' 
                              : trade.status === 'FILLED'
                                ? 'Đã khớp lệnh'
                                : 'Đã huỷ'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <Link 
                          to={`/trade/${trade.id}`} 
                          className="text-primary-600 hover:text-primary-900 mr-4"
                        >
                          Xem
                        </Link>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan="8" className="px-6 py-4 text-center text-sm text-gray-500">
                      Không tìm thấy giao dịch nào phù hợp
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

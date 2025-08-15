import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://192.168.56.56:5000/api/v1';

const TradeContext = createContext();

export const TradeProvider = ({ children }) => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({
    status: 'all',
    symbol: '',
    bot: '',
  });
  const [balance, setBalance] = useState({
    available: 0,
    equity: 0,
    used_margin: 0,
    wallet_balance: 0,
    loading: true,
    error: null
  });

  // Lấy số dư tài khoản
  const fetchBalance = async () => {
    try {
      setBalance(prev => ({ ...prev, loading: true, error: null }));
      const response = await axios.get(`${API_URL}/balance`);
      setBalance({
        available: response.data.available_balance || 0,
        equity: response.data.equity || 0,
        used_margin: response.data.used_margin || 0,
        wallet_balance: response.data.wallet_balance || 0,
        loading: false,
        error: null
      });
    } catch (err) {
      console.error('Lỗi khi lấy số dư:', err);
      setBalance(prev => ({
        ...prev,
        loading: false,
        error: 'Không thể tải số dư tài khoản'
      }));
    }
  };

  // Lấy danh sách giao dịch
  const fetchTrades = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/trades`, { params: filters });
      setTrades(response.data);
      setError(null);
    } catch (err) {
      console.error('Lỗi khi lấy danh sách giao dịch:', err);
      setError('Không thể tải dữ liệu giao dịch');
    } finally {
      setLoading(false);
    }
  };

  // Huỷ lệnh
  const cancelOrder = async (orderId) => {
    try {
      await axios.post(`${API_URL}/order/cancel`, { order_id: orderId });
      // Làm mới danh sách sau khi huỷ
      fetchTrades();
      return { success: true };
    } catch (err) {
      console.error('Lỗi khi huỷ lệnh:', err);
      return { success: false, error: err.response?.data?.error || 'Lỗi khi huỷ lệnh' };
    }
  };

  // Lấy chi tiết giao dịch
  const fetchTradeDetail = async (tradeId) => {
    try {
      const response = await axios.get(`${API_URL}/trade/${tradeId}`);
      return response.data;
    } catch (err) {
      console.error('Lỗi khi lấy chi tiết giao dịch:', err);
      throw err;
    }
  };

  // Lọc giao dịch dựa trên bộ lọc
  const filteredTrades = trades.filter(trade => {
    if (filters.status !== 'all' && trade.status !== filters.status) return false;
    if (filters.symbol && !trade.asset?.toLowerCase().includes(filters.symbol.toLowerCase())) return false;
    if (filters.bot && !trade.bot?.toLowerCase().includes(filters.bot.toLowerCase())) return false;
    return true;
  });

  // Tự động lấy dữ liệu khi filters thay đổi
  useEffect(() => {
    fetchTrades();
    fetchBalance();
    
    // Cập nhật số dư mỗi phút
    const interval = setInterval(fetchBalance, 60000);
    return () => clearInterval(interval);
  }, [filters]);

  return (
    <TradeContext.Provider
      value={{
        trades: filteredTrades,
        loading,
        error,
        filters,
        setFilters,
        fetchTrades,
        fetchBalance,
        balance,
        cancelOrder,
        fetchTradeDetail,
        refreshTrades: fetchTrades,
      }}
    >
      {children}
    </TradeContext.Provider>
  );
};

export const useTrades = () => {
  const context = useContext(TradeContext);
  if (!context) {
    throw new Error('useTrades phải được sử dụng bên trong TradeProvider');
  }
  return context;
};

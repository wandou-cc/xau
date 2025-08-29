import MetaTrader5 as mt5
from ..config import Config
import logging
from typing import Optional, Dict, List, Any, Tuple
from functools import wraps
import time

def retry_on_error(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        print(f"⚠️ {func.__name__} 失败，{delay}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        time.sleep(delay)
                    else:
                        print(f"❌ {func.__name__} 最终失败: {e}")
            raise last_exception
        return wrapper
    return decorator

class MT5Client:
    def __init__(self):
        self.connected: bool = False
        self.symbol: str = Config.XAUUSD_SYMBOL
        self.account_info: Optional[Any] = None
        self._symbol_info_cache: Optional[Any] = None
        self._last_symbol_info_update: float = 0
        self._symbol_info_cache_ttl: float = 300  # 5分钟缓存
        self._initialize()

    def _initialize(self) -> bool:
        """初始化MT5连接"""
        try:
            if not mt5.initialize():
                error_code = mt5.last_error()
                print(f"❌ MT5初始化失败，错误代码: {error_code}")
                return False
            
            # 显示网络模式
            network_type = "模拟账户" if Config.USE_TESTNET else "真实账户"
            print(f"🔧 MT5 配置为 {network_type} 模式")
            
            # 检查交易品种是否可用，如果不可用则自动查找黄金品种
            if not self._check_and_set_symbol():
                return False
            
            # 获取账户信息
            self._get_account_info()
            
            self.connected = True
            print(f"✅ MT5连接成功，使用品种: {self.symbol}")
            return True
            
        except Exception as e:
            print(f"❌ MT5初始化失败: {e}")
            self.connected = False
            return False
    
    def _check_and_set_symbol(self) -> bool:
        """检查并设置交易品种"""
        try:
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                # 自动查找黄金品种
                symbols = mt5.symbols_get()
                if symbols:
                    gold_symbols = [s.name for s in symbols if 'XAU' in s.name or 'GOLD' in s.name]
                    if gold_symbols:
                        self.symbol = gold_symbols[0]
                        print(f"🔄 自动切换到黄金品种: {self.symbol}")
                    else:
                        print("❌ 未找到黄金相关交易品种")
                        return False
                else:
                    print("❌ 无法获取交易品种列表")
                    return False
            
            # 验证品种信息
            if not self._validate_symbol_info():
                return False
                
            return True
            
        except Exception as e:
            print(f"❌ 检查交易品种失败: {e}")
            return False
    
    def _validate_symbol_info(self) -> bool:
        """验证品种信息"""
        try:
            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                print(f"❌ 无法获取品种信息: {self.symbol}")
                return False
            
            # 检查品种是否启用
            if not symbol_info.visible:
                if not mt5.symbol_select(self.symbol, True):
                    print(f"❌ 无法启用品种: {self.symbol}")
                    return False
            
            # 缓存品种信息
            self._symbol_info_cache = symbol_info
            self._last_symbol_info_update = time.time()
            
            print(f"✅ 品种验证成功: {self.symbol}")
            return True
            
        except Exception as e:
            print(f"❌ 验证品种信息失败: {e}")
            return False

    def _get_account_info(self) -> None:
        """获取账户信息"""
        try:
            self.account_info = mt5.account_info()
            if self.account_info:
                # 根据配置显示预期的账户类型
                expected_type = "模拟账户" if Config.USE_TESTNET else "真实账户"
                actual_type = "模拟账户" if self.account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "真实账户"
                
                print(f"📊 账户类型: {actual_type}")
                if Config.USE_TESTNET and actual_type == "真实账户":
                    print("⚠️ 警告: 配置为测试模式但连接了真实账户!")
                elif not Config.USE_TESTNET and actual_type == "模拟账户":
                    print("⚠️ 警告: 配置为主网模式但连接了模拟账户!")
                    
                print(f"💰 账户余额: {self.account_info.balance:.2f} {self.account_info.currency}")
                print(f"💳 可用保证金: {self.account_info.margin_free:.2f} {self.account_info.currency}")
                print(f"⚡ 杠杆: 1:{self.account_info.leverage}")
            else:
                print("⚠️ 无法获取账户信息")
        except Exception as e:
            print(f"❌ 获取账户信息失败: {e}")
            self.account_info = None

    def _is_connected(self) -> bool:
        """检查连接状态"""
        if not self.connected:
            print("❌ MT5未连接")
            return False
        return True

    def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """获取MT5账户余额详情"""
        if not self._is_connected():
            return None
            
        try:
            # 刷新账户信息
            self.account_info = mt5.account_info()
            if not self.account_info:
                print("❌ 无法获取MT5账户信息")
                return None
            
            # 获取账户详细信息
            balance = self.account_info.balance
            equity = self.account_info.equity
            margin = self.account_info.margin
            margin_free = self.account_info.margin_free
            margin_level = self.account_info.margin_level if self.account_info.margin > 0 else 0
            profit = self.account_info.profit
            currency = self.account_info.currency
            leverage = self.account_info.leverage
            
            # 判断账户类型
            account_type = "模拟账户" if self.account_info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "真实账户"
            expected_type = "模拟账户" if Config.USE_TESTNET else "真实账户"
            
            # 计算风险指标
            margin_ratio = (margin / equity * 100) if equity > 0 else 0
            free_margin_ratio = (margin_free / equity * 100) if equity > 0 else 0
            
            print(f"   净值: {equity:.2f} {currency} | 可用: {margin_free:.2f} {currency} | 盈亏: {profit:+.2f} {currency} ({account_type})")
            print(f"   保证金率: {margin_ratio:.1f}% | 可用保证金率: {free_margin_ratio:.1f}%")
            
            # 检查账户类型是否匹配配置
            if Config.USE_TESTNET and account_type == "真实账户":
                print("   ⚠️ 警告: 配置为测试模式但连接了真实账户!")
            elif not Config.USE_TESTNET and account_type == "模拟账户":
                print("   ⚠️ 警告: 配置为主网模式但连接了模拟账户!")
            
            return {
                'balance': balance,
                'equity': equity,
                'margin': margin,
                'margin_free': margin_free,
                'margin_level': margin_level,
                'profit': profit,
                'currency': currency,
                'leverage': leverage,
                'account_type': account_type,
                'trade_mode': self.account_info.trade_mode,
                'margin_ratio': margin_ratio,
                'free_margin_ratio': free_margin_ratio
            }
            
        except Exception as e:
            print(f"❌ 获取MT5账户余额失败: {e}")
            return None

    def get_available_margin(self) -> Optional[float]:
        """获取可用保证金"""
        if not self._is_connected() or not self.account_info:
            return None
        return self.account_info.margin_free

    @retry_on_error(max_retries=3, delay=0.5)
    def get_xauusd_price(self) -> Optional[float]:
        """获取XAUUSD当前价格"""
        if not self._is_connected():
            return None
            
        try:
            tick = mt5.symbol_info_tick(self.symbol)
            if tick is None:
                print(f"❌ 无法获取 {self.symbol} 的价格数据")
                return None
            
            price = tick.bid
            if price <= 0:
                print(f"⚠️ 获取到无效价格: {price}")
                return None
                
            return price
            
        except Exception as e:
            print(f"❌ 获取XAUUSD价格失败: {e}")
            return None

    def _get_symbol_info(self) -> Optional[Any]:
        """获取品种信息（带缓存）"""
        current_time = time.time()
        
        # 检查缓存是否有效
        if (self._symbol_info_cache and 
            current_time - self._last_symbol_info_update < self._symbol_info_cache_ttl):
            return self._symbol_info_cache
        
        # 重新获取品种信息
        if self._validate_symbol_info():
            return self._symbol_info_cache
        
        return None

    def place_order(self, order_type: int, volume: float, price: Optional[float] = None, 
                   stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Optional[Any]:
        """下单交易
        
        Args:
            order_type: 订单类型 (mt5.ORDER_TYPE_BUY 或 mt5.ORDER_TYPE_SELL)
            volume: 交易量（手数）
            price: 价格，None表示市价单
            stop_loss: 止损价格
            take_profit: 止盈价格
        """
        if not self._is_connected():
            return None
            
        try:
            # 获取品种信息
            symbol_info = self._get_symbol_info()
            if symbol_info is None:
                print(f"❌ 无法获取品种信息: {self.symbol}")
                return None
                
            # 如果品种未启用，则启用
            if not symbol_info.visible:
                if not mt5.symbol_select(self.symbol, True):
                    print(f"❌ 无法启用品种: {self.symbol}")
                    return None
            
            # 构建订单请求
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": self.symbol,
                "volume": volume,
                "type": order_type,
                "deviation": 20,  # 允许的价格偏差
                "magic": 234000,  # 魔术数字
                "comment": "python script order",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # 设置价格
            if price:
                request["price"] = price
                
            # 设置止损和止盈
            if stop_loss:
                request["sl"] = stop_loss
            if take_profit:
                request["tp"] = take_profit
            
            # 发送订单
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"❌ 下单失败，错误代码: {result.retcode}, 描述: {result.comment}")
                return None
            else:
                print(f"✅ 下单成功，订单号: {result.order}, 成交价格: {result.price}")
                return result
                
        except Exception as e:
            print(f"❌ 下单失败: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_open_positions(self) -> List[Any]:
        """获取XAUUSD持仓"""
        if not self._is_connected():
            if not self._initialize():
                return []
            
        try:
            # 只获取当前使用的黄金品种的持仓
            positions = mt5.positions_get(symbol=self.symbol)
            if positions is None:
                return []
            
            # 过滤有效持仓
            active_positions = [p for p in positions if getattr(p, 'volume', 0) > 0]
            
            if active_positions:
                print(f"📊 发现 {len(active_positions)} 个活跃XAUUSD持仓")
            
            return active_positions
        except Exception as e:
            print(f"❌ 获取MT5 XAUUSD持仓失败: {e}")
            return []

    def close_position(self, ticket: int) -> bool:
        """关闭指定持仓
        
        Args:
            ticket: 持仓单号
        """
        if not self._is_connected():
            return False
            
        try:
            position = mt5.positions_get(ticket=ticket)
            if not position:
                print(f"❌ 未找到持仓: {ticket}")
                return False
                
            position = position[0]
            
            # 构建平仓请求
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": mt5.ORDER_TYPE_BUY if position.type == mt5.POSITION_TYPE_SELL else mt5.ORDER_TYPE_SELL,
                "position": ticket,
                "deviation": 20,
                "magic": 234000,
                "comment": "python script close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"❌ 平仓失败，错误代码: {result.retcode}, 描述: {result.comment}")
                return False
            else:
                print(f"✅ 平仓成功，订单号: {result.order}")
                return True
                
        except Exception as e:
            print(f"❌ 平仓失败: {e}")
            return False

    def get_trade_history(self, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[Any]:
        """获取交易历史
        
        Args:
            start_date: 开始日期 (datetime对象)
            end_date: 结束日期 (datetime对象)
        """
        if not self._is_connected():
            return []
            
        try:
            history = mt5.history_deals_get(start_date, end_date)
            if history is None:
                return []
            return history
        except Exception as e:
            print(f"❌ 获取交易历史失败: {e}")
            return []

    def calculate_recent_pnl(self, minutes: int = 5) -> Tuple[float, int]:
        """计算最近几分钟的已实现盈亏"""
        try:
            from datetime import datetime, timedelta
            
            # 计算时间范围
            now = datetime.now()
            start_time = now - timedelta(minutes=minutes)
            
            # 获取最近的交易历史
            history = self.get_trade_history(start_time, now)
            if not history:
                return 0.0, 0
            
            total_pnl = 0.0
            trade_count = 0
            
            for deal in history:
                # 只计算与当前黄金品种相关的交易
                if getattr(deal, 'symbol', '') == self.symbol:
                    profit = getattr(deal, 'profit', 0)
                    total_pnl += profit
                    trade_count += 1
            
            return total_pnl, trade_count
            
        except Exception as e:
            print(f"❌ 计算MT5已实现盈亏失败: {e}")
            return 0.0, 0

    def refresh_account_info(self) -> None:
        """刷新账户信息"""
        self._get_account_info()

    def close_all_positions(self) -> bool:
        """市价全平XAUUSD持仓"""
        if not self._is_connected():
            return False
            
        try:
            positions = self.get_open_positions()
            if not positions:
                print("✅ MT5无XAUUSD持仓需要平仓")
                return True
            
            success_count = 0
            total_volume = 0.0
            
            for pos in positions:
                pos_volume = getattr(pos, 'volume', 0)
                pos_type = getattr(pos, 'type', 0)
                ticket = getattr(pos, 'ticket', 0)
                
                if pos_volume == 0:
                    continue
                    
                # 根据持仓类型确定平仓方向
                close_type = mt5.ORDER_TYPE_SELL if pos_type == 0 else mt5.ORDER_TYPE_BUY
                close_type_str = "SELL" if pos_type == 0 else "BUY"
                total_volume += pos_volume
                
                print(f"📤 MT5平仓: {close_type_str} {pos_volume}手 (单号:{ticket})")
                
                # 构建平仓请求
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": self.symbol,
                    "volume": pos_volume,
                    "type": close_type,
                    "position": ticket,  # 指定要平仓的持仓单号
                    "deviation": 20,
                    "magic": 234000,
                    "comment": "close all positions",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                try:
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"✅ MT5平仓成功: 订单号 {result.order}")
                        success_count += 1
                    else:
                        print(f"❌ MT5平仓失败: 错误代码 {result.retcode}, 描述: {result.comment}")
                except Exception as e:
                    print(f"❌ MT5平仓错误: {e}")
            
            if success_count > 0:
                print(f"🎯 平仓完成: 成功平仓 {success_count} 个持仓，总计 {total_volume} 手")
            
            return success_count > 0
            
        except Exception as e:
            print(f"❌ MT5全平失败: {e}")
            return False

    def place_xauusd_order(self, action: str, volume: float) -> Optional[Any]:
        """
        下XAUUSD订单
        :param action: 'buy' or 'sell'
        :param volume: 交易量（手数）
        """
        if not self._is_connected():
            return None
            
        try:
            # 转换动作为MT5订单类型
            order_type = mt5.ORDER_TYPE_BUY if action.lower() == 'buy' else mt5.ORDER_TYPE_SELL
            
            # 使用基础下单方法
            result = self.place_order(
                order_type=order_type,
                volume=volume
            )
            
            if result:
                print(f"✅ MT5 {action.upper()} 订单成功:")
                print(f"   交易对: {self.symbol}")
                print(f"   方向: {action.upper()}")
                print(f"   数量: {volume} 手")
                print(f"   订单号: {result.order}")
            
            return result
            
        except Exception as e:
            print(f"❌ MT5下单失败: {e}")
            return None
    
    def get_account_status(self) -> Dict[str, Any]:
        """获取账户状态概览"""
        try:
            balance = self.get_account_balance()
            positions = self.get_open_positions()
            
            return {
                'connected': self._is_connected(),
                'symbol': self.symbol,
                'balance': balance,
                'positions_count': len(positions) if positions else 0,
                'account_type': balance.get('account_type', '未知') if balance else '未知',
                'network_type': '测试网' if Config.USE_TESTNET else '主网'
            }
        except Exception as e:
            print(f"❌ 获取账户状态失败: {e}")
            return {'connected': False, 'error': str(e)}

    def __del__(self):
        """清理资源"""
        try:
            if self.connected:
                mt5.shutdown()
        except Exception as e:
            print(f"⚠️ 关闭MT5连接失败: {e}")
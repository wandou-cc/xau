from binance.client import Client
from binance.exceptions import BinanceAPIException
from src.config import Config
import math
import time
from typing import Optional, Dict, List, Tuple, Any
from functools import wraps

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

class BinanceClient:
    def __init__(self):
        self.client: Optional[Client] = None
        self._step_size_cache: Dict[str, float] = {}
        self._last_step_size_update = 0
        self._step_size_cache_ttl = 3600  # 1小时缓存
        self._initialize_client()
    
    def _initialize_client(self) -> bool:
        """初始化Binance客户端"""
        try:
            # 设置代理
            kwargs = {}
            if Config.USE_PROXY:
                kwargs['proxies'] = {
                    'http': Config.PROXY_URL,
                    'https': Config.PROXY_URL
                }

            # 初始化客户端
            self.client = Client(
                Config.BINANCE_API_KEY,
                Config.BINANCE_API_SECRET,
                requests_params=kwargs,
            )
            
            # 根据统一配置决定使用测试网还是主网
            if Config.USE_TESTNET:
                try:
                    self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
                except Exception:
                    pass
            
            # 测试连接
            self.client.futures_ping()
            print("✅ Binance客户端初始化成功")
            return True
            
        except Exception as e:
            print(f"❌ Binance客户端初始化失败: {e}")
            self.client = None
            return False
    
    def _is_client_ready(self) -> bool:
        """检查客户端是否就绪"""
        if not self.client:
            print("❌ Binance客户端未初始化")
            return False
        return True
    
    @retry_on_error(max_retries=3, delay=1.0)
    def get_paxg_price(self) -> Optional[float]:
        """获取期货价格（使用配置交易对）"""
        if not self._is_client_ready():
            return None
            
        try:
            ticker = self.client.futures_symbol_ticker(symbol=Config.PAXG_SYMBOL)
            price = float(ticker['price'])
            return price if price > 0 else None
        except (BinanceAPIException, KeyError, ValueError) as e:
            print(f"❌ 获取PAXG价格失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 获取PAXG价格时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_paxg_depth(self) -> Optional[Dict[str, Any]]:
        """获取期货市场深度"""
        if not self._is_client_ready():
            return None
            
        try:
            depth = self.client.futures_order_book(symbol=Config.PAXG_SYMBOL)
            return depth
        except BinanceAPIException as e:
            print(f"❌ 获取PAXG深度失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 获取PAXG深度时发生未知错误: {e}")
            return None

    def _get_futures_step_size(self, symbol: str) -> float:
        """获取期货步进大小（带缓存）"""
        current_time = time.time()
        
        # 检查缓存是否有效
        if (symbol in self._step_size_cache and 
            current_time - self._last_step_size_update < self._step_size_cache_ttl):
            return self._step_size_cache[symbol]
        
        try:
            info = self.client.futures_exchange_info()
            for s in info.get('symbols', []):
                if s.get('symbol') == symbol:
                    for f in s.get('filters', []):
                        if f.get('filterType') == 'LOT_SIZE':
                            step = f.get('stepSize')
                            step_size = float(step) if step is not None else 0.001
                            
                            # 更新缓存
                            self._step_size_cache[symbol] = step_size
                            self._last_step_size_update = current_time
                            return step_size
            
            # 默认值
            default_step = 0.001
            self._step_size_cache[symbol] = default_step
            self._last_step_size_update = current_time
            return default_step
            
        except Exception as e:
            print(f"⚠️ 获取步进大小失败，使用默认值: {e}")
            return 0.001

    @retry_on_error(max_retries=2, delay=0.5)
    def set_leverage(self, symbol: Optional[str] = None, leverage: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """设置期货合约杠杆"""
        if not self._is_client_ready():
            return None
            
        try:
            symbol = symbol or Config.PAXG_SYMBOL
            leverage = leverage or Config.OPEN_LEVEL
            
            # 确保杠杆是整数且在有效范围内
            leverage = int(leverage)
            if leverage < 1 or leverage > 125:
                print(f"⚠️ 杠杆倍数{leverage}超出范围(1-125)，使用默认值1")
                leverage = 1
            
            result = self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            return result
            
        except BinanceAPIException as e:
            # 如果是杠杆已经设置为相同值的错误，不视为失败
            if "leverage not modified" in str(e).lower():
                return {"leverage": leverage, "symbol": symbol}
            else:
                print(f"❌ 设置杠杆失败: {e}")
                return None
        except Exception as e:
            print(f"❌ 设置杠杆时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_position_mode(self) -> bool:
        """获取持仓模式"""
        if not self._is_client_ready():
            return False
            
        try:
            result = self.client.futures_get_position_mode()
            # dualSidePosition: true=对冲持仓模式, false=单向持仓模式
            return result.get('dualSidePosition', False)
        except Exception as e:
            print(f"⚠️ 获取持仓模式失败，使用默认值: {e}")
            return False  # 默认为单向持仓模式

    @retry_on_error(max_retries=2, delay=0.5)
    def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """获取Binance合约账户余额"""
        if not self._is_client_ready():
            return None
            
        try:
            account_info = self.client.futures_account()
            if not account_info:
                print("❌ 获取Binance账户信息失败: 返回数据为空")
                return None
            
            # 提取关键数据
            total_wallet_balance = float(account_info.get('totalWalletBalance', 0))
            total_unrealized_pnl = float(account_info.get('totalUnrealizedProfit', 0))
            total_margin_balance = float(account_info.get('totalMarginBalance', 0))
            available_balance = float(account_info.get('availableBalance', 0))
            total_initial_margin = float(account_info.get('totalInitialMargin', 0))
            total_maint_margin = float(account_info.get('totalMaintMargin', 0))
            
            # 计算风险指标
            margin_ratio = (total_maint_margin / total_margin_balance * 100) if total_margin_balance > 0 else 0
            free_margin_ratio = (available_balance / total_margin_balance * 100) if total_margin_balance > 0 else 0
            
            network_type = "测试网" if Config.USE_TESTNET else "主网"
            print(f"   总权益: {total_margin_balance:.2f} USDT | 可用: {available_balance:.2f} USDT | 盈亏: {total_unrealized_pnl:+.2f} USDT ({network_type})")
            print(f"   保证金率: {margin_ratio:.1f}% | 可用保证金率: {free_margin_ratio:.1f}%")
            
            # 获取各币种余额
            assets = account_info.get('assets', [])
            non_zero_assets = []
            for asset in assets:
                wallet_balance = float(asset.get('walletBalance', 0))
                if wallet_balance > 0:
                    non_zero_assets.append({
                        'asset': asset.get('asset', ''),
                        'wallet_balance': wallet_balance,
                        'unrealized_profit': float(asset.get('unrealizedProfit', 0)),
                        'margin_balance': float(asset.get('marginBalance', 0))
                    })
            
            return {
                'total_wallet_balance': total_wallet_balance,
                'total_margin_balance': total_margin_balance,
                'available_balance': available_balance,
                'total_unrealized_pnl': total_unrealized_pnl,
                'total_initial_margin': total_initial_margin,
                'total_maint_margin': total_maint_margin,
                'margin_ratio': margin_ratio,
                'free_margin_ratio': free_margin_ratio,
                'assets': non_zero_assets,
                'network_type': network_type
            }
            
        except BinanceAPIException as e:
            print(f"❌ 获取Binance合约账户余额失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 获取Binance合约账户余额时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """获取PAXG持仓"""
        if not self._is_client_ready():
            return []
            
        try:
            positions = self.client.futures_position_information(symbol=Config.PAXG_SYMBOL)
            # 只返回有持仓量的PAXG仓位
            active_positions = [p for p in positions if float(p.get('positionAmt', 0)) != 0]
            
            if active_positions:
                print(f"📊 发现 {len(active_positions)} 个活跃PAXG持仓")
            
            return active_positions
        except Exception as e:
            print(f"❌ 获取Binance PAXG持仓失败: {e}")
            return []

    @retry_on_error(max_retries=2, delay=0.5)
    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的交易记录"""
        if not self._is_client_ready():
            return []
            
        try:
            trades = self.client.futures_account_trades(symbol=Config.PAXG_SYMBOL, limit=limit)
            return trades
        except BinanceAPIException as e:
            print(f"❌ 获取Binance交易记录失败: {e}")
            return []
        except Exception as e:
            print(f"❌ 获取Binance交易记录时发生未知错误: {e}")
            return []

    def calculate_recent_pnl(self, minutes: int = 5) -> Tuple[float, int]:
        """计算最近几分钟的已实现盈亏"""
        try:
            from datetime import datetime, timedelta
            
            # 获取最近的交易记录
            trades = self.get_recent_trades(limit=50)
            if not trades:
                return 0.0, 0
            
            # 计算时间范围
            now = datetime.now()
            time_threshold = now - timedelta(minutes=minutes)
            time_threshold_ms = int(time_threshold.timestamp() * 1000)
            
            total_pnl = 0.0
            trade_count = 0
            
            for trade in trades:
                trade_time = int(trade.get('time', 0))
                if trade_time >= time_threshold_ms:
                    realized_pnl = float(trade.get('realizedPnl', 0))
                    total_pnl += realized_pnl
                    trade_count += 1
            
            return total_pnl, trade_count
            
        except Exception as e:
            print(f"❌ 计算Binance已实现盈亏失败: {e}")
            return 0.0, 0

    def close_all_positions(self) -> bool:
        """市价全平PAXG持仓"""
        if not self._is_client_ready():
            return False
            
        try:
            positions = self.get_open_positions()
            if not positions:
                print("✅ Binance无PAXG持仓需要平仓")
                return True
            
            # 检查持仓模式
            is_hedge_mode = self.get_position_mode()
            mode_str = "对冲持仓模式" if is_hedge_mode else "单向持仓模式"
            print(f"🔧 Binance当前模式: {mode_str}")
            
            success_count = 0
            total_quantity = 0.0
            
            for pos in positions:
                pos_amt = float(pos.get('positionAmt', 0))
                if pos_amt == 0:
                    continue
                    
                # 根据持仓方向确定平仓方向
                close_side = "SELL" if pos_amt > 0 else "BUY"
                close_quantity = abs(pos_amt)
                pos_side = pos.get('positionSide', 'BOTH')
                total_quantity += close_quantity
                
                print(f"📤 Binance平仓: {close_side} {close_quantity:.4f} PAXG (持仓方向: {pos_side})")
                
                # 构建平仓订单参数
                order_params = {
                    'symbol': Config.PAXG_SYMBOL,
                    'side': close_side,
                    'type': 'MARKET',  # 市价单
                    'quantity': close_quantity
                }
                
                # 根据持仓模式设置参数
                if is_hedge_mode:
                    # 双向持仓模式：必填positionSide，不接受reduceOnly参数
                    if pos_side in ['LONG', 'SHORT']:
                        order_params['positionSide'] = pos_side
                    else:
                        print(f"⚠️ 对冲模式下持仓方向异常: {pos_side}，跳过此持仓")
                        continue
                else:
                    # 单向持仓模式：可选positionSide（默认BOTH），可使用reduceOnly
                    order_params['positionSide'] = 'BOTH'
                    order_params['reduceOnly'] = True  # 只减仓，不开新仓
                
                print(f"   订单参数: {order_params}")
                
                try:
                    order = self.client.futures_create_order(**order_params)
                    if order:
                        print(f"✅ Binance平仓成功: 订单ID {order.get('orderId')}")
                        success_count += 1
                    else:
                        print(f"❌ Binance平仓失败: 返回空结果")
                except Exception as e:
                    print(f"❌ Binance平仓错误: {e}")
            
            if success_count > 0:
                print(f"🎯 平仓完成: 成功平仓 {success_count} 个持仓，总计 {total_quantity:.4f} PAXG")
            
            return success_count > 0
            
        except Exception as e:
            print(f"❌ Binance全平失败: {e}")
            return False

    def place_paxg_order(self, side: str, quantity_usdt: float) -> Optional[Dict[str, Any]]:
        """
        期货下单（测试网/主网由统一配置决定）
        :param side: 'BUY' or 'SELL'
        :param quantity_usdt: 以USDT计价的名义金额
        """
        if not self._is_client_ready():
            return None
            
        try:
            # 获取当前价格来计算数量
            price = self.get_paxg_price()
            if price is None:
                print("❌ 无法获取PAXG价格，下单失败")
                return None

            # 计算数量，按步进截断
            raw_qty = quantity_usdt / price
            step = self._get_futures_step_size(Config.PAXG_SYMBOL)
            quantity = math.floor(raw_qty / step) * step
            
            if quantity <= 0:
                print(f"❌ 下单数量过小: {quantity} (原始: {raw_qty}, 步进: {step})")
                return None

            # 检查持仓模式
            is_hedge_mode = self.get_position_mode()
            mode_str = "对冲持仓模式" if is_hedge_mode else "单向持仓模式"
            
            # 构建订单参数
            order_params = {
                'symbol': Config.PAXG_SYMBOL,
                'side': side,
                'type': 'MARKET',
                'quantity': quantity
            }
            
            # 如果是对冲持仓模式，需要指定positionSide
            if is_hedge_mode:
                if side == 'BUY':
                    order_params['positionSide'] = 'LONG'
                else:  # SELL
                    order_params['positionSide'] = 'SHORT'
                print(f"🔧 Binance持仓模式: {mode_str}, positionSide: {order_params['positionSide']}")
            else:
                print(f"🔧 Binance持仓模式: {mode_str}, 不使用positionSide参数")
            
            # 期货市价单
            order = self.client.futures_create_order(**order_params)
            
            network_type = "测试网" if Config.USE_TESTNET else "主网"
            print(f"✅ Binance {side} 订单成功 ({network_type}):")
            print(f"   交易对: {Config.PAXG_SYMBOL}")
            print(f"   方向: {side}")
            print(f"   数量: {quantity} PAXG")
            print(f"   金额: ~{quantity_usdt:.2f} USDT")
            print(f"   订单ID: {order.get('orderId')}")
            
            return order
            
        except BinanceAPIException as e:
            print(f"❌ Binance下单失败: {e}")
            return None
        except Exception as e:
            print(f"❌ 下单过程中发生未知错误: {e}")
            return None
    
    def get_account_status(self) -> Dict[str, Any]:
        """获取账户状态概览"""
        try:
            balance = self.get_account_balance()
            positions = self.get_open_positions()
            position_mode = self.get_position_mode()
            
            return {
                'connected': self._is_client_ready(),
                'balance': balance,
                'positions_count': len(positions) if positions else 0,
                'position_mode': '对冲' if position_mode else '单向',
                'network_type': '测试网' if Config.USE_TESTNET else '主网'
            }
        except Exception as e:
            print(f"❌ 获取账户状态失败: {e}")
            return {'connected': False, 'error': str(e)}
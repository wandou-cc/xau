from okx.MarketData import MarketAPI
from okx.Trade import TradeAPI
from okx.Account import AccountAPI
from okx.PublicData import PublicAPI
from ..config import Config
import math
import time
from typing import Optional, Dict, List, Any, Tuple
from functools import wraps
import logging

# 配置日志
logger = logging.getLogger(__name__)

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
                        logger.warning(f"⚠️ {func.__name__} 失败，{delay}秒后重试 ({attempt + 1}/{max_retries}): {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"❌ {func.__name__} 最终失败: {e}")
            raise last_exception
        return wrapper
    return decorator

class OKXClient:
    def __init__(self):
        # 初始化状态
        self._initialized = False
        self._step_size_cache: Dict[str, float] = {}
        self._last_step_size_update: float = 0
        self._step_size_cache_ttl: float = 3600  # 1小时缓存
        self._instruments_cache: Dict[str, Any] = {}
        self._last_instruments_update: float = 0
        self._instruments_cache_ttl: float = 1800  # 30分钟缓存
        
        # 初始化OKX API客户端
        self._initialize_client()
    
    def _initialize_client(self) -> bool:
        """初始化OKX API客户端"""
        try:
            # 根据统一配置决定使用测试网还是主网
            flag = "1" if Config.USE_TESTNET else "0"  # 0: 生产环境, 1: 模拟环境
            
            # OKX API的代理配置
            proxy = None
            if Config.USE_PROXY and Config.PROXY_URL:
                proxy = Config.PROXY_URL
            
            # 初始化各种API客户端
            self.market_api = MarketAPI(
                api_key=Config.OKX_API_KEY,
                api_secret_key=Config.OKX_API_SECRET,
                passphrase=Config.OKX_PASSPHRASE,
                flag=flag,
                proxy=proxy
            )
            
            self.trade_api = TradeAPI(
                api_key=Config.OKX_API_KEY,
                api_secret_key=Config.OKX_API_SECRET,
                passphrase=Config.OKX_PASSPHRASE,
                flag=flag,
                proxy=proxy
            )
            
            self.account_api = AccountAPI(
                api_key=Config.OKX_API_KEY,
                api_secret_key=Config.OKX_API_SECRET,
                passphrase=Config.OKX_PASSPHRASE,
                flag=flag,
                proxy=proxy
            )
            
            self.public_api = PublicAPI(
                flag=flag,
                proxy=proxy
            )
            
            # 测试连接
            self._test_connection()
            
            self._initialized = True
            network_type = "模拟盘" if Config.USE_TESTNET else "实盘"
            logger.info(f"✅ OKX客户端初始化成功 ({network_type})")
            return True
            
        except Exception as e:
            logger.error(f"❌ OKX客户端初始化失败: {e}")
            self._initialized = False
            raise
    
    def _test_connection(self) -> bool:
        """测试API连接"""
        try:
            # 尝试获取账户信息来测试连接
            test_result = self.account_api.get_account_balance()
            if test_result and test_result.get('code') == '0':
                return True
            else:
                raise Exception(f"API连接测试失败: {test_result.get('msg', '未知错误') if test_result else '请求失败'}")
        except Exception as e:
            logger.error(f"❌ OKX连接测试失败: {e}")
            raise
    
    def _is_initialized(self) -> bool:
        """检查客户端是否已初始化"""
        if not self._initialized:
            logger.error("❌ OKX客户端未初始化")
            return False
        return True
    
    def _validate_response(self, response: Optional[Dict[str, Any]], operation: str) -> bool:
        """验证API响应"""
        if not response:
            logger.error(f"❌ {operation}: 响应为空")
            return False
        
        code = response.get('code')
        if code != '0':
            msg = response.get('msg', '未知错误')
            logger.error(f"❌ {operation}: 错误代码 {code}, 消息: {msg}")
            return False
        
        return True

    @retry_on_error(max_retries=3, delay=1.0)
    def get_xauusd_price(self) -> Optional[float]:
        """获取OKX XAUUSD价格"""
        if not self._is_initialized():
            return None
            
        try:
            ticker = self.market_api.get_ticker(
                instId=Config.OKX_XAUUSD_SYMBOL
            )
            
            if not self._validate_response(ticker, "获取XAUUSD价格"):
                return None
            
            data = ticker.get('data', [])
            if data and len(data) > 0:
                price = float(data[0].get('last', 0))
                if price > 0:
                    return price
                else:
                    logger.warning(f"⚠️ 获取到无效价格: {price}")
                    return None
            
            logger.error("❌ 价格数据为空")
            return None
            
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"❌ 解析XAUUSD价格失败: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 获取XAUUSD价格时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def set_leverage(self, symbol: Optional[str] = None, leverage: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """设置期货合约杠杆"""
        if not self._is_initialized():
            return None
            
        try:
            symbol = symbol or Config.OKX_XAUUSD_SYMBOL
            leverage = leverage or Config.OPEN_LEVEL
            
            # 确保杠杆是数字且在有效范围内
            leverage = float(leverage)
            if leverage < 1 or leverage > 100:
                logger.warning(f"⚠️ OKX杠杆倍数{leverage}超出范围(1-100)，使用默认值1")
                leverage = 1
            
            # OKX设置杠杆需要指定交易模式，这里使用全仓模式
            result = self.account_api.set_leverage(
                instId=symbol,
                lever=str(leverage),
                mgnMode="cross"  # 全仓模式
            )
            
            if result and result.get('code') == '0':
                logger.info(f"✅ OKX杠杆设置成功: {symbol} {leverage}x")
                return result
            else:
                error_msg = result.get('msg', '未知错误') if result else '请求失败'
                # 检查是否是杠杆未变更的错误
                if "leverage not modified" in error_msg.lower() or "已设置" in error_msg:
                    logger.info(f"ℹ️ OKX杠杆已设置为 {leverage}x")
                    return {"leverage": leverage, "symbol": symbol, "status": "already_set"}
                else:
                    logger.error(f"❌ OKX杠杆设置失败: {error_msg}")
                    return None
                    
        except Exception as e:
            logger.error(f"❌ OKX杠杆设置时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_account_balance(self) -> Optional[Dict[str, Any]]:
        """获取账户保证金余额"""
        if not self._is_initialized():
            return None
            
        try:
            account_info = self.account_api.get_account_balance()
            
            if not self._validate_response(account_info, "获取账户余额"):
                return None
            
            data = account_info.get('data', [])
            if not data:
                logger.error("❌ 账户数据为空")
                return None
            
            account_data = data[0]
            total_eq = float(account_data.get('totalEq', 0))  # 总权益
            frozen_bal = float(account_data.get('frozenBal', 0))  # 冻结余额
            
            # 获取各币种详细余额，特别是USDT的可用余额
            balance_details = account_data.get('details', [])
            usdt_available = 0.0
            non_zero_assets = []
            
            network_type = "模拟盘" if Config.USE_TESTNET else "实盘"
            
            # 显示各币种详细余额并计算USDT可用余额
            for detail in balance_details:
                eq = float(detail.get('eq', 0))
                if eq > 0:  # 只显示有余额的币种
                    ccy = detail.get('ccy', '')
                    avail_bal = float(detail.get('availBal', 0))
                    
                    # 获取USDT的可用余额
                    if ccy == 'USDT':
                        usdt_available = avail_bal
                    
                    non_zero_assets.append({
                        'currency': ccy,
                        'equity': eq,
                        'available': avail_bal
                    })
            
            # 计算风险指标
            margin_ratio = (frozen_bal / total_eq * 100) if total_eq > 0 else 0
            free_margin_ratio = (usdt_available / total_eq * 100) if total_eq > 0 else 0
            
            logger.info(f"   总权益: {total_eq:.2f} USDT | 可用: {usdt_available:.2f} USDT | 冻结: {frozen_bal:.2f} USDT ({network_type})")
            logger.info(f"   保证金率: {margin_ratio:.1f}% | 可用保证金率: {free_margin_ratio:.1f}%")
            
            return {
                'total_equity': total_eq,
                'available_balance': usdt_available,  # 使用USDT的实际可用余额
                'frozen_balance': frozen_bal,
                'usdt_available': usdt_available,  # 明确的USDT可用余额字段
                'margin_ratio': margin_ratio,
                'free_margin_ratio': free_margin_ratio,
                'details': non_zero_assets,
                'network_type': network_type
            }
            
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"❌ 解析OKX账户余额失败: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ 获取OKX账户保证金时发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """获取XAUT-USDT持仓"""
        if not self._is_initialized():
            return []
            
        try:
            positions = self.account_api.get_positions(instId=Config.OKX_XAUUSD_SYMBOL)
            
            if not self._validate_response(positions, "获取持仓信息"):
                return []
            
            # 只返回有持仓量的XAUT-USDT仓位
            open_positions = []
            for pos in positions.get('data', []):
                pos_size = float(pos.get('pos', 0))
                if pos_size != 0:
                    open_positions.append(pos)
            
            if open_positions:
                logger.info(f"📊 发现 {len(open_positions)} 个活跃XAUT-USDT持仓")
            
            return open_positions
            
        except (ValueError, KeyError, TypeError) as e:
            logger.error(f"❌ 解析OKX持仓数据失败: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ 获取OKX XAUT-USDT持仓时发生未知错误: {e}")
            return []

    def _get_instruments_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取交易品种信息（带缓存）"""
        current_time = time.time()
        
        # 检查缓存是否有效
        if (symbol in self._instruments_cache and 
            current_time - self._last_instruments_update < self._instruments_cache_ttl):
            return self._instruments_cache[symbol]
        
        try:
            instruments = self.public_api.get_instruments(
                instType="SWAP",
                instId=symbol
            )
            
            if self._validate_response(instruments, "获取品种信息"):
                data = instruments.get('data', [])
                if data:
                    # 更新缓存
                    self._instruments_cache[symbol] = data[0]
                    self._last_instruments_update = current_time
                    return data[0]
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ 获取品种信息失败: {e}")
            return None

    def _get_trading_step_size(self, symbol: str) -> float:
        """获取交易步长"""
        try:
            instrument_info = self._get_instruments_info(symbol)
            if instrument_info:
                lot_sz = instrument_info.get('lotSz', '1')
                return float(lot_sz)
            return 1.0
        except Exception:
            return 1.0

    @retry_on_error(max_retries=2, delay=0.5)
    def get_recent_trades(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的交易记录"""
        if not self._is_initialized():
            return []
            
        try:
            # 获取最近的成交记录
            trades = self.trade_api.get_fills(
                instId=Config.OKX_XAUUSD_SYMBOL,
                limit=str(limit)
            )
            
            if not self._validate_response(trades, "获取交易记录"):
                return []
            
            return trades.get('data', [])
            
        except Exception as e:
            logger.error(f"❌ 获取OKX交易记录时发生未知错误: {e}")
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
                trade_time = int(trade.get('ts', 0))
                if trade_time >= time_threshold_ms:
                    # 获取手续费（负数）
                    fee = float(trade.get('fee', 0))
                    # 计算交易盈亏（买卖差价，这里简化处理）
                    fill_px = float(trade.get('fillPx', 0))
                    fill_sz = float(trade.get('fillSz', 0))
                    side = trade.get('side', '')
                    
                    # 这里主要记录手续费成本
                    total_pnl += fee  # 手续费是负数
                    trade_count += 1
            
            return total_pnl, trade_count
            
        except Exception as e:
            logger.error(f"❌ 计算OKX已实现盈亏失败: {e}")
            return 0.0, 0

    @retry_on_error(max_retries=2, delay=0.5)
    def close_all_positions(self) -> bool:
        """市价全平XAUUSD持仓"""
        if not self._is_initialized():
            return False
            
        try:
            positions = self.get_open_positions()
            if not positions:
                logger.info("✅ OKX无XAUUSD持仓需要平仓")
                return True
            
            success_count = 0
            total_contracts = 0
            
            for pos in positions:
                pos_size = float(pos.get('pos', 0))
                pos_side = pos.get('posSide', 'net')
                
                if pos_size == 0:
                    continue
                
                total_contracts += abs(pos_size)
                logger.info(f"📤 OKX平仓: {pos_side.upper()} {abs(pos_size):.0f}张")
                
                # 使用专门的平仓接口
                close_params = {
                    "instId": Config.OKX_XAUUSD_SYMBOL,
                    "mgnMode": "cross",  # 全仓模式
                    "posSide": pos_side,  # 持仓方向
                    "ccy": "USDT"
                }
                
                try:
                    # 调用平仓接口
                    result = self.trade_api.close_positions(**close_params)
                    if result and result.get('code') == '0':
                        logger.info(f"✅ OKX平仓成功: {pos_side.upper()} 持仓已平")
                        success_count += 1
                    else:
                        error_msg = result.get('msg', '未知错误') if result else '请求失败'
                        logger.error(f"❌ OKX平仓失败: {error_msg}")
                except Exception as e:
                    logger.error(f"❌ OKX平仓错误: {e}")
            
            if success_count > 0:
                logger.info(f"🎯 平仓完成: 成功平仓 {success_count} 个持仓，总计 {total_contracts:.0f} 张")
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ OKX全平时发生未知错误: {e}")
            return False

    @retry_on_error(max_retries=2, delay=0.5)
    def place_xauusd_order(self, side: str, quantity_contracts: float) -> Optional[Dict[str, Any]]:
        """
        期货下单（模拟盘/实盘由统一配置决定）
        :param side: 'buy' or 'sell'
        :param quantity_contracts: 合约张数（对于XAUT-USDT，1张=0.001盎司）
        """
        if not self._is_initialized():
            return None
            
        try:
            # 获取交易步长
            step = self._get_trading_step_size(Config.OKX_XAUUSD_SYMBOL)
            
            # 按步进截断
            quantity = math.floor(quantity_contracts / step) * step
            ounces = quantity / 1000  # 张数转换为盎司数
            
            if quantity <= 0:
                logger.error(f"❌ OKX下单数量过小: {quantity} (原始: {quantity_contracts}, 步进: {step})")
                return None

            logger.info(f"🔧 OKX下单数量: {quantity:.0f}张 (= {ounces:.3f}盎司)")

            # 根据买卖方向确定持仓方向
            if side.lower() == "buy":
                pos_side = "long"  # 买入开多
            else:  # sell
                pos_side = "short"  # 卖出开空
            
            # 构建下单参数
            order_params = {
                "instId": Config.OKX_XAUUSD_SYMBOL,
                "tdMode": "cross",  # 全仓模式
                "side": side,
                "posSide": pos_side,  # 持仓方向
                "ordType": "market",
                "sz": str(quantity),
                "ccy": "USDT",  # 保证金币种
            }
            
            # 期货市价单
            order = self.trade_api.place_order(**order_params)

            if order and order.get('code') == '0':
                network_type = "模拟盘" if Config.USE_TESTNET else "实盘"
                logger.info(f"✅ OKX {side.upper()} 订单成功 ({network_type}):")
                logger.info(f"   交易对: {Config.OKX_XAUUSD_SYMBOL}")
                logger.info(f"   方向: {side.upper()}")
                logger.info(f"   数量: {quantity:.0f}张 ({ounces:.3f}盎司)")
                
                order_data = order.get('data', [])
                if order_data:
                    logger.info(f"   订单ID: {order_data[0].get('ordId')}")
                
                return order
            else:
                error_msg = order.get('sMsg', '未知错误') if order else '请求失败'
                logger.error(f"❌ OKX下单失败: {error_msg}")
                return None
            
        except Exception as e:
            logger.error(f"❌ OKX下单过程中发生未知错误: {e}")
            return None

    @retry_on_error(max_retries=2, delay=0.5)
    def get_xauusd_depth(self) -> Optional[List[Dict[str, Any]]]:
        """获取市场深度"""
        if not self._is_initialized():
            return None
            
        try:
            depth = self.market_api.get_books(
                instId=Config.OKX_XAUUSD_SYMBOL,
                sz='20'  # 获取20档深度
            )
            
            if self._validate_response(depth, "获取市场深度"):
                return depth.get('data', [])
            
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取OKX市场深度时发生未知错误: {e}")
            return None
    
    def get_account_status(self) -> Dict[str, Any]:
        """获取账户状态概览"""
        try:
            balance = self.get_account_balance()
            positions = self.get_open_positions()
            
            return {
                'initialized': self._is_initialized(),
                'symbol': Config.OKX_XAUUSD_SYMBOL,
                'balance': balance,
                'positions_count': len(positions) if positions else 0,
                'network_type': '模拟盘' if Config.USE_TESTNET else '实盘'
            }
        except Exception as e:
            logger.error(f"❌ 获取账户状态失败: {e}")
            return {'initialized': False, 'error': str(e)}
    
    def refresh_cache(self) -> None:
        """刷新缓存数据"""
        try:
            self._step_size_cache.clear()
            self._instruments_cache.clear()
            self._last_step_size_update = 0
            self._last_instruments_update = 0
            logger.info("✅ OKX缓存已刷新")
        except Exception as e:
            logger.warning(f"⚠️ 刷新缓存失败: {e}")
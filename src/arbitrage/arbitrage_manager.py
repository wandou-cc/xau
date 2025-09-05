from ..exchanges.binance_client import BinanceClient
from ..exchanges.okx_client import OKXClient
from ..config import Config
from ..dingtalk_notifier import DingTalkNotifier
from ..trading_time import trading_time_manager, is_trading_time, wait_until_trading_time
import time
import json
import os
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from functools import wraps
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def safe_execute(func_name: str = "未知操作"):
    """安全执行装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"❌ {func_name} 执行失败: {e}")
                return None
        return wrapper
    return decorator

class ArbitrageManager:
    def __init__(self):
        logger.info("🔧 正在初始化交易客户端...")
        
        # 初始化状态
        self._shutdown_called = False
        self._initialization_success = False
        
        try:
            # 始终初始化Binance（用于PAXG交易）
            self.binance = BinanceClient()
            if not self.binance.client:
                raise Exception("Binance客户端初始化失败")
            binance_status = "✅ Binance"
            
            # 根据配置初始化XAUUSD交易所
            if Config.USE_XAU_OKX:
                try:
                    self.okx = OKXClient()
                    self.mt5 = None  # 不使用MT5
                    xau_status = "✅ OKX"
                except Exception as e:
                    logger.error(f"❌ OKX初始化失败: {e}")
                    raise
            else:
                try:
                    from ..exchanges.mt5_client import MT5Client
                    self.mt5 = MT5Client()
                    if not self.mt5.connected:
                        raise Exception("MT5客户端连接失败")
                    self.okx = None  # 不使用OKX
                    xau_status = "✅ MT5"
                except Exception as e:
                    logger.error(f"❌ MT5初始化失败: {e}")
                    raise
            
            # 显示客户端初始化状态
            network_type = "测试网" if Config.USE_TESTNET else "主网"
            
            # 获取Binance持仓模式信息
            try:
                is_hedge_mode = self.binance.get_position_mode()
                position_mode = "对冲持仓" if is_hedge_mode else "单向持仓"
            except Exception:
                position_mode = "未知"
            
            logger.info(f"📡 客户端状态: {binance_status} ({network_type}, {position_mode}) | {xau_status} ({'模拟盘' if Config.USE_TESTNET and self.okx else '实盘' if self.okx else 'XAUUSD'})")
            
            # 设置杠杆
            self._initialize_leverage()
            
            # 显示账户保证金信息
            self._show_account_balance()
            
            # 校验账户余额
            self._validate_account_balance()
            
            # 初始化钉钉通知器
            self.dingtalk_notifier = None
            if Config.USE_DINGTALK:
                try:
                    self.dingtalk_notifier = DingTalkNotifier()
                    logger.info("✅ 钉钉通知模块初始化成功")
                except Exception as e:
                    logger.warning(f"⚠️ 钉钉通知模块初始化失败: {e}")
            else:
                logger.info("📵 钉钉通知功能已禁用")
            
            # 交易状态管理
            self.position_open = False
            self.current_position = None
            self.trade_id = 0
            
            # 价差统计管理
            self.max_diff = float('-inf')
            self.min_diff = float('inf')
            self.max_diff_time = None
            self.min_diff_time = None
            
            # 运行时统计
            self.start_time = datetime.now()
            self.total_trades_count = 0
            self.total_system_profit = 0.0
            
            # 交易时间状态跟踪
            self.last_trading_status = None
            
            # 定时推送管理
            self.position_notification_enabled = Config.ENABLE_POSITION_NOTIFICATION
            self.position_notification_times = Config.POSITION_NOTIFICATION_TIMES
            self.last_notification_date = None  # 跟踪最后一次推送的日期，防止重复推送
            
            # 发送启动通知
            if self.dingtalk_notifier:
                try:
                    self.dingtalk_notifier.send_system_startup_notification()
                    logger.info("📱 系统启动通知已发送")
                except Exception as e:
                    logger.warning(f"⚠️ 发送启动通知失败: {e}")
            
            self._initialization_success = True
            logger.info("✅ 套利管理器初始化完成")
            
        except Exception as e:
            logger.error(f"❌ 套利管理器初始化失败: {e}")
            self.shutdown_system(f"初始化失败: {str(e)[:100]}", True)
            raise
    
    def _initialize_leverage(self) -> None:
        """初始化时设置期货杠杆"""
        try:
            # 设置Binance杠杆
            binance_result = self.binance.set_leverage(Config.PAXG_SYMBOL, Config.OPEN_LEVEL)
            binance_status = "✅" if binance_result is not None else "⚠️"
            
            # 如果使用OKX的XAUUSD，也设置OKX杠杆
            if self.okx:
                okx_result = self.okx.set_leverage(Config.OKX_XAUUSD_SYMBOL, Config.OPEN_LEVEL)
                okx_status = "✅" if okx_result is not None else "⚠️"
                logger.info(f"⚡ 杠杆设置: Binance {binance_status} | OKX {okx_status} ({Config.OPEN_LEVEL}x)")
            else:
                logger.info(f"⚡ 杠杆设置: Binance {binance_status} ({Config.OPEN_LEVEL}x)")
                
        except Exception as e:
            logger.error(f"❌ 杠杆设置失败: {e}")
    
    @safe_execute("显示账户余额")
    def _show_account_balance(self) -> None:
        """显示所有交易所账户保证金信息"""
        logger.info(f"\n💰 账户余额信息:")
        logger.info("-" * 50)
        
        # 显示Binance合约账户信息
        logger.info("🏢 Binance:")
        binance_balance = self.binance.get_account_balance()
        if not binance_balance:
            logger.error("   ❌ 获取Binance账户信息失败")
        
        # 显示XAUUSD交易所账户信息
        if self.okx:
            logger.info("🏢 OKX:")
            okx_balance = self.okx.get_account_balance()
            if not okx_balance:
                logger.error("   ❌ 获取OKX账户信息失败")
        elif self.mt5:
            logger.info("🏢 MT5:")
            mt5_balance = self.mt5.get_account_balance()
            if not mt5_balance:
                logger.error("   ❌ 获取MT5账户信息失败")
        
        logger.info("-" * 50)
    
    @safe_execute("校验账户余额")
    def _validate_account_balance(self) -> None:
        """校验账户余额是否足够进行套利交易"""
        logger.info(f"🔍 余额校验:")
        
        validation_passed = True
        min_required_balance = 50.0  # 最低要求50 USDT余额作为安全缓冲
        
        # 校验Binance余额
        binance_balance = self.binance.get_account_balance()
        if binance_balance:
            available = binance_balance.get('available_balance', 0)
            if available >= min_required_balance:
                logger.info(f"   ✅ Binance: {available:.2f} USDT 充足")
            else:
                logger.warning(f"   ❌ Binance: {available:.2f} USDT 不足 (需要≥{min_required_balance:.0f})")
                validation_passed = False
        else:
            logger.error("   ❌ Binance: 获取余额失败")
            validation_passed = False
        
        # 校验XAUUSD交易所余额
        if self.okx:
            okx_balance = self.okx.get_account_balance()
            if okx_balance:
                available = okx_balance.get('available_balance', 0)
                if available >= min_required_balance:
                    logger.info(f"   ✅ OKX: {available:.2f} USDT 充足")
                else:
                    logger.warning(f"   ❌ OKX: {available:.2f} USDT 不足 (需要≥{min_required_balance:.0f})")
                    validation_passed = False
            else:
                logger.error("   ❌ OKX: 获取余额失败")
                validation_passed = False
                
        elif self.mt5:
            mt5_balance = self.mt5.get_account_balance()
            if mt5_balance:
                available = mt5_balance.get('margin_free', 0)
                currency = mt5_balance.get('currency', 'USD')
                if available >= min_required_balance:
                    logger.info(f"   ✅ MT5: {available:.2f} {currency} 充足")
                else:
                    logger.warning(f"   ❌ MT5: {available:.2f} {currency} 不足 (需要≥{min_required_balance:.0f})")
                    validation_passed = False
            else:
                logger.error("   ❌ MT5: 获取余额失败")
                validation_passed = False
        
        if validation_passed:
            logger.info("   ✅ 余额校验通过，可开始交易")
        else:
            logger.warning("   ⚠️ 余额不足，建议充值后交易")
        logger.info("-" * 50)
    
    @safe_execute("计算交易盈利")
    def _calculate_total_profit_after_close(self) -> None:
        """平仓后计算合计盈利"""
        try:
            logger.info("\n⏳ 等待10秒后计算交易盈利...")
            time.sleep(10)
            
            logger.info("\n📊 计算交易合计盈利:")
            logger.info("-" * 40)
            
            total_profit = 0.0
            total_trades = 0
            
            # 初始化变量
            okx_pnl, okx_trades = 0.0, 0
            mt5_pnl, mt5_trades = 0.0, 0
            
            # 获取Binance最近5分钟的盈利
            binance_pnl, binance_trades = self.binance.calculate_recent_pnl(minutes=5)
            logger.info(f"🏢 Binance PAXG:")
            logger.info(f"   交易数量: {binance_trades}")
            logger.info(f"   已实现盈亏: {binance_pnl:+.4f} USDT")
            total_profit += binance_pnl
            total_trades += binance_trades
            
            # 获取XAUUSD交易所的盈利
            if self.okx:
                okx_pnl, okx_trades = self.okx.calculate_recent_pnl(minutes=5)
                logger.info(f"🏢 OKX XAUUSD:")
                logger.info(f"   交易数量: {okx_trades}")
                logger.info(f"   手续费: {okx_pnl:+.4f} USDT")
                total_profit += okx_pnl
                total_trades += okx_trades
                
            elif self.mt5:
                mt5_pnl, mt5_trades = self.mt5.calculate_recent_pnl(minutes=5)
                logger.info(f"🏢 MT5 XAUUSD:")
                logger.info(f"   交易数量: {mt5_trades}")
                logger.info(f"   已实现盈亏: {mt5_pnl:+.4f} USD")
                total_profit += mt5_pnl
                total_trades += mt5_trades
            
            logger.info("-" * 40)
            logger.info(f"💰 本轮套利合计:")
            logger.info(f"   总交易数: {total_trades}")
            logger.info(f"   总盈亏: {total_profit:+.4f} USDT")
            
            # 计算年化收益率（基于可用余额）
            try:
                binance_balance = self.binance.get_account_balance()
                if binance_balance:
                    available_balance = binance_balance.get('available_balance', 100)
                    if available_balance > 0:
                        profit_rate = (total_profit / available_balance) * 100
                        logger.info(f"   收益率: {profit_rate:+.4f}%")
            except:
                pass
                
            logger.info("-" * 40)
            
            # 更新系统总盈利统计
            self.total_system_profit += total_profit
            
            # 发送钉钉盈利汇总通知
            if self.dingtalk_notifier:
                try:
                    profit_data = {
                        'total_profit': total_profit,
                        'total_trades': total_trades,
                        'binance_pnl': binance_pnl,
                        'binance_trades': binance_trades,
                        'exchange_pnl': okx_pnl if self.okx else mt5_pnl,
                        'exchange_trades': okx_trades if self.okx else mt5_trades,
                        'exchange_name': "OKX" if self.okx else "MT5",
                        'profit_rate': (total_profit / available_balance * 100) if 'available_balance' in locals() and available_balance > 0 else 0,
                        'timestamp': datetime.now()
                    }
                    self.dingtalk_notifier.send_arbitrage_profit_notification(profit_data)
                except Exception as e:
                    logger.warning(f"⚠️ 发送盈利汇总通知失败: {e}")
            
        except Exception as e:
            logger.error(f"❌ 计算交易盈利失败: {e}")
    
    def shutdown_system(self, shutdown_reason: str = "正常关闭", is_error: bool = False) -> None:
        """优雅关闭系统并发送通知"""
        # 防止重复调用
        if self._shutdown_called:
            return
        try:
            self._shutdown_called = True
            logger.info(f"\n🛑 正在关闭套利交易系统... 原因: {shutdown_reason}")
            
            # 发送关闭通知
            if self.dingtalk_notifier:
                try:
                    runtime_info = {
                        'start_time': self.start_time,
                        'total_trades': self.total_trades_count, 
                        'total_profit': self.total_system_profit,
                        'max_diff': self.max_diff if self.max_diff != float('-inf') else 0,
                        'min_diff': self.min_diff if self.min_diff != float('inf') else 0,
                        'shutdown_reason': shutdown_reason,
                        'is_error_shutdown': is_error
                    }
                    self.dingtalk_notifier.send_system_shutdown_notification(runtime_info)
                    logger.info("📱 系统关闭通知已发送")
                except Exception as e:
                    logger.warning(f"⚠️ 发送关闭通知失败: {e}")
            
            logger.info("✅ 系统已安全关闭")
            
        except Exception as e:
            logger.error(f"❌ 系统关闭过程中发生错误: {e}")
        
    def get_prices(self) -> Tuple[Optional[float], Optional[float]]:
        """Get PAXG and XAUUSD prices"""
        try:
            paxg_price = self.binance.get_paxg_price()
            if paxg_price is None:
                return None, None
            
            # 根据初始化的客户端获取XAUUSD价格
            if self.okx:
                xauusd_price = self.okx.get_xauusd_price()
            elif self.mt5:
                xauusd_price = self.mt5.get_xauusd_price()
            else:
                logger.error("❌ 未初始化任何XAUUSD交易所客户端")
                return None, None
                
            if xauusd_price is None:
                return None, None
                
            return paxg_price, xauusd_price
        except Exception as e:
            logger.error(f"❌ 获取价格失败: {e}")
            return None, None

    def log_trade(self, trade_type: str, action: str, paxg_price: float, xauusd_price: float, 
                  diff: float, binance_position_size: Optional[float] = None, 
                  xau_volume: Optional[float] = None, profit: Optional[float] = None) -> None:
        """记录交易到文件"""
        try:
            trade_record = {
                "trade_id": self.trade_id,
                "timestamp": datetime.now().isoformat(),
                "trade_type": trade_type,  # "OPEN" or "CLOSE" 
                "action": action,
                "paxg_price": paxg_price,
                "xauusd_price": xauusd_price,
                "price_diff": diff,
                "binance_position_size": binance_position_size,
                "xau_volume": xau_volume,  # 通用的XAUUSD仓位大小（手数或USDT）
                "exchange_type": "OKX" if self.okx else "MT5",  # 记录使用的交易所
                "profit": profit
            }
            
            # 写入文件
            with open(Config.TRADE_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(trade_record, ensure_ascii=False) + '\n')
            
        except Exception as e:
            logger.warning(f"⚠️ 记录交易日志失败: {e}")

    def update_diff_stats(self, diff: float, paxg_price: float, xauusd_price: float) -> None:
        """更新并记录价差统计信息"""
        current_time = datetime.now()
        updated = False
        
        # 更新最大差值
        if diff > self.max_diff:
            self.max_diff = diff
            self.max_diff_time = current_time
            updated = True
            
        # 更新最小差值
        if diff < self.min_diff:
            self.min_diff = diff
            self.min_diff_time = current_time
            updated = True
            
        # 如果有更新，记录到文件
        if updated:
            try:
                stats_record = {
                    "timestamp": current_time.isoformat(),
                    "current_diff": diff,
                    "paxg_price": paxg_price,
                    "xauusd_price": xauusd_price,
                    "max_diff": self.max_diff,
                    "max_diff_time": self.max_diff_time.isoformat() if self.max_diff_time else None,
                    "min_diff": self.min_diff,
                    "min_diff_time": self.min_diff_time.isoformat() if self.min_diff_time else None,
                    "diff_range": self.max_diff - self.min_diff
                }
                
                with open(Config.DIFF_STATS_FILE, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(stats_record, ensure_ascii=False) + '\n')
                
            except Exception as e:
                logger.warning(f"⚠️ 记录价差统计失败: {e}")

    @safe_execute("开仓操作")
    def open_position(self, paxg_price: float, xauusd_price: float, diff: float) -> bool:
        """实际开仓（基于实际持仓检查）"""
        # 检查是否已有实际持仓
        binance_positions = self.binance.get_open_positions()
        if self.okx:
            xau_positions = self.okx.get_open_positions()
            exchange_name = "OKX"
        elif self.mt5:
            xau_positions = self.mt5.get_open_positions()
            exchange_name = "MT5"
        else:
            logger.error("❌ 未初始化任何XAUUSD交易所客户端")
            return False
        
        # 如果已有持仓，跳过开仓
        if binance_positions and len(binance_positions) > 0:
            logger.warning(f"⚠️ Binance已有{len(binance_positions)}个PAXG持仓，跳过开仓")
            return False
        
        if xau_positions and len(xau_positions) > 0:
            logger.warning(f"⚠️ {exchange_name}已有{len(xau_positions)}个黄金持仓，跳过开仓")
            return False
            
        try:
            self.trade_id += 1
            
            # 动态计算仓位大小
            # Binance: 开0.01盎司PAXG
            paxg_quantity = Config.PAXG_QUANTITY  # 开仓PAXG数量
            binance_position_size_usdt = paxg_quantity * paxg_price  # 用于传给下单函数
            
            # XAUUSD交易所仓位大小（根据初始化的客户端）
            if self.okx:
                # OKX: 按照相同盎司数量 = 0.01盎司 = 10张 (1张 = 0.001盎司)
                xau_volume = paxg_quantity * 1000  # 0.01盎司 = 10张
                volume_unit = "张"
            elif self.mt5:
                # MT5: 开0.01手 (0.01手 = 1盎司，最小下单单位)
                xau_volume = paxg_quantity / 100
                volume_unit = "手"
            else:
                logger.error("❌ 未初始化任何XAUUSD交易所客户端")
                return False
            
            if diff > 0:
                # PAXG价格高，卖PAXG买XAUUSD
                action = "SELL PAXG, LONG XAUUSD"
                position_type = "SHORT_PAXG_LONG_XAU"
                paxg_side = "SELL"
                xau_action = "BUY"
            else:
                # PAXG价格低，买PAXG卖XAUUSD  
                action = "BUY PAXG, SHORT XAUUSD"
                position_type = "LONG_PAXG_SHORT_XAU"
                paxg_side = "BUY"
                xau_action = "SELL"
            
            logger.info(f"🟢 开始执行套利开仓...")
            logger.info(f"   交易ID: {self.trade_id}")
            logger.info(f"   动作: {action}")
            logger.info(f"   价差: {diff:.2f}")
            logger.info(f"   Binance: {paxg_quantity}盎司PAXG (价格${paxg_price:.2f}, 价值${binance_position_size_usdt:.2f})")
            
            if self.okx:
                okx_ounces = xau_volume / 1000  # 张数转换为盎司数
                logger.info(f"   OKX: {xau_volume:.0f}张黄金 = {okx_ounces:.3f}盎司 (价格${xauusd_price:.2f}, 价值${okx_ounces * xauusd_price:.2f})")
            elif self.mt5:
                logger.info(f"   MT5: {xau_volume}手XAUUSD = {xau_volume * 100}盎司 (价格${xauusd_price:.2f}, 价值${xauusd_price * xau_volume * 100:.2f})")
            
            # 1. 在Binance执行PAXG交易
            paxg_order = self.binance.place_paxg_order(paxg_side, binance_position_size_usdt)
            if paxg_order is None:
                logger.error("❌ PAXG下单失败，取消套利")
                return False
                
            # 2. 在相应交易所执行XAUUSD交易
            if self.okx:
                xau_result = self.okx.place_xauusd_order(xau_action.lower(), xau_volume)  # xau_volume是张数
                exchange_name = "OKX"
            elif self.mt5:
                xau_result = self.mt5.place_xauusd_order(xau_action.lower(), xau_volume)  # xau_volume是手数
                exchange_name = "MT5"
            else:
                logger.error("❌ 未初始化任何XAUUSD交易所客户端")
                return False
            
            if xau_result is None:
                logger.warning(f"⚠️ {exchange_name} XAUUSD下单可能失败，但PAXG已执行")
                # 这里在实际环境中应该回滚PAXG交易
                
            # 记录开仓（不再维护内部状态，完全依赖实际持仓）
            self.position_open = True  # 临时保留，等完全迁移完后可删除
            self.current_position = None  # 不再使用
            
            # 记录开仓
            self.log_trade("OPEN", action, paxg_price, xauusd_price, diff, binance_position_size_usdt, xau_volume)
            
            logger.info(f"✅ 套利开仓完成!")
            logger.info(f"   XAUUSD交易: {'成功' if xau_result else '模拟'}")
            
            if self.okx:
                okx_ounces = xau_volume / 1000  # 张数转换为盎司数
                logger.info(f"   实际仓位 - Binance: {paxg_quantity}盎司PAXG(${binance_position_size_usdt:.2f}), OKX: {xau_volume:.0f}张({okx_ounces:.3f}盎司)")
            elif self.mt5:
                logger.info(f"   实际仓位 - Binance: {paxg_quantity}盎司PAXG(${binance_position_size_usdt:.2f}), MT5: {xau_volume}手({xau_volume * 100}盎司)")
            
            # 更新系统统计
            self.total_trades_count += 1
            
            # 发送钉钉开仓通知
            if self.dingtalk_notifier:
                try:
                    trade_data = {
                        'trade_id': self.trade_id,
                        'action': action,
                        'paxg_price': paxg_price,
                        'xauusd_price': xauusd_price,
                        'price_diff': diff,
                        'paxg_quantity': paxg_quantity,
                        'xau_volume': xau_volume,
                        'exchange_type': "OKX" if self.okx else "MT5",
                        'timestamp': datetime.now()
                    }
                    self.dingtalk_notifier.send_arbitrage_open_notification(trade_data)
                except Exception as e:
                    logger.warning(f"⚠️ 发送开仓通知失败: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 开仓失败: {e}")
            return False

    @safe_execute("平仓操作")
    def close_position(self, paxg_price: float, xauusd_price: float, diff: float) -> bool:
        """市价全平所有持仓"""
        try:
            logger.info(f"🔴 开始执行市价全平...")
            logger.info(f"   当前价差: {diff:.2f}")
            
            # 全平 Binance PAXG 持仓
            binance_success = self.binance.close_all_positions()
            
            # 全平 XAUUSD 持仓
            xau_success = False
            if self.okx:
                xau_success = self.okx.close_all_positions()
                exchange_name = "OKX"
            elif self.mt5:
                xau_success = self.mt5.close_all_positions()
                exchange_name = "MT5"
            else:
                logger.error("❌ 未初始化任何XAUUSD交易所客户端")
                return False
            
            # 记录平仓（简化版）
            if binance_success or xau_success:
                self.log_trade("CLOSE", "MARKET_CLOSE_ALL", paxg_price, xauusd_price, diff, 0, 0, 0)
            
            # 显示结果
            if binance_success and xau_success:
                logger.info(f"✅ 全平完成! (Binance ✅ | {exchange_name} ✅)")
            elif binance_success:
                logger.warning(f"⚠️ 部分平仓完成 (Binance ✅ | {exchange_name} ❌)")
            elif xau_success:
                logger.warning(f"⚠️ 部分平仓完成 (Binance ❌ | {exchange_name} ✅)")
            else:
                logger.error(f"❌ 平仓失败 (Binance ❌ | {exchange_name} ❌)")
                return False
            
            # 重置内部状态
            self.position_open = False
            self.current_position = None
            
            # 发送钉钉平仓通知
            if self.dingtalk_notifier:
                try:
                    trade_data = {
                        'paxg_price': paxg_price,
                        'xauusd_price': xauusd_price,
                        'price_diff': diff,
                        'exchange_type': "OKX" if self.okx else "MT5",
                        'timestamp': datetime.now()
                    }
                    self.dingtalk_notifier.send_arbitrage_close_notification(trade_data)
                except Exception as e:
                    logger.warning(f"⚠️ 发送平仓通知失败: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 平仓失败: {e}")
            return False

    def should_close_position(self, diff: float, binance_positions: List[Dict[str, Any]] = None, 
                              xau_positions: List[Any] = None) -> bool:
        """判断是否应该平仓（基于已获取的持仓信息）"""
        # 如果没有传入持仓信息，则获取（向后兼容）
        if binance_positions is None or xau_positions is None:
            binance_positions = self.binance.get_open_positions()
            if self.okx:
                xau_positions = self.okx.get_open_positions()
            elif self.mt5:
                xau_positions = self.mt5.get_open_positions()
            else:
                xau_positions = []
        
        has_positions = (binance_positions and len(binance_positions) > 0) or (xau_positions and len(xau_positions) > 0)
        
        if not has_positions:
            return False
            
        # 当价差回归到较小范围时平仓
        return abs(diff) <= Config.CLOSE_PRICE_DIFF

    def monitor_prices(self) -> None:
        """Monitor prices and manage positions"""
        if not self._initialization_success:
            logger.error("❌ 系统未成功初始化，无法启动监控")
            return
            
        logger.info("\n🚀 启动套利交易监控系统")
        logger.info("=" * 60)
        if self.okx:
            logger.info(f"💰 策略: Binance{Config.PAXG_QUANTITY}盎司PAXG ⇄ OKX(1000张XAUT-USDT=1盎司)")
        elif self.mt5:
            logger.info(f"💰 策略: Binance{Config.PAXG_QUANTITY}盎司PAXG ⇄ MT5(1手XAUUSD=100盎司)")
        logger.info(f"📊 阈值: 开仓±{Config.MIN_PRICE_DIFF:.2f} | 平仓±{Config.CLOSE_PRICE_DIFF:.2f} | 间隔{Config.PRICE_CHECK_INTERVAL}s")
        logger.info(f"⏰ 交易时间校验: {'✅ 启用' if Config.ENABLE_TRADING_TIME_CHECK else '❌ 禁用'}")
        
        # 显示定时推送配置
        if self.position_notification_enabled and self.position_notification_times:
            times_str = ', '.join(self.position_notification_times)
            logger.info(f"📱 定时推送: ✅ 启用 ({times_str})")
        else:
            logger.info(f"📱 定时推送: ❌ 禁用")
        
        logger.info("=" * 60)
        
        # 显示交易时间信息（如果启用了交易时间校验）
        if Config.ENABLE_TRADING_TIME_CHECK:
            logger.info("\n🕐 交易时间信息:")
            logger.info(trading_time_manager.get_trading_schedule_info())
            
            # 检查当前是否在交易时间并初始化状态
            is_trading, trading_status = is_trading_time()
            self.last_trading_status = is_trading  # 初始化交易状态
            if not is_trading:
                logger.info(f"⏰ 当前不在交易时间: {trading_status}")
                logger.info("⏳ 等待交易时间开始...")
                try:
                    wait_until_trading_time(60)  # 每60秒检查一次
                    logger.info("✅ 交易时间开始，开始监控价格")
                    # 更新状态并发送开盘通知
                    self._check_and_notify_trading_status_change()
                except KeyboardInterrupt:
                    logger.info("⌨️ 用户中断等待，系统退出")
                    return
        else:
            logger.info("\n⏰ 交易时间校验已禁用，将24小时运行")
            logger.info("⚠️ 注意：在非交易时间进行交易可能导致失败或异常")
            # 即使禁用了交易时间校验，也初始化状态为True
            self.last_trading_status = True
        
        consecutive_errors = 0
        max_consecutive_errors = 5
        
        while not self._shutdown_called:
            try:
                # 检查是否仍在交易时间（如果启用了交易时间校验）
                if Config.ENABLE_TRADING_TIME_CHECK:
                    is_trading, trading_status = self._check_and_notify_trading_status_change()
                    if not is_trading:
                        logger.info(f"\n⏰ 进入休市时间: {trading_status}")
                        logger.info("⏳ 等待下次交易时间...")
                        try:
                            wait_until_trading_time(60)  # 每60秒检查一次
                            logger.info("✅ 交易时间恢复，继续监控价格")
                            # 重置错误计数
                            consecutive_errors = 0
                            continue
                        except KeyboardInterrupt:
                            logger.info("⌨️ 用户中断等待，系统退出")
                            break
                
                paxg_price, xauusd_price = self.get_prices()
                if paxg_price is None or xauusd_price is None:
                    consecutive_errors += 1
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error(f"❌ 连续{consecutive_errors}次获取价格失败，系统即将关闭")
                        self.shutdown_system(f"连续{consecutive_errors}次获取价格失败", True)
                        break
                    logger.warning(f"\r⚠️ 获取价格失败，重试中... ({consecutive_errors}/{max_consecutive_errors})")
                    time.sleep(Config.PRICE_CHECK_INTERVAL)
                    continue

                # 重置错误计数
                consecutive_errors = 0
                
                diff = paxg_price - xauusd_price
                current_time = datetime.now().strftime("%H:%M:%S")
                
                # 更新价差统计（跟随循环执行）
                self.update_diff_stats(diff, paxg_price, xauusd_price)
                
                # 检查定时推送
                self._check_and_send_scheduled_notification(paxg_price, xauusd_price, diff)
                
                # 简化的价格显示
                print(f"\r[{current_time}] PAXG: ${paxg_price:.2f} | XAUUSD: ${xauusd_price:.2f} | 价差: {diff:+.2f} | 范围: [{self.min_diff:.2f}, {self.max_diff:.2f}]", end="")
                
                # 检查是否有持仓
                binance_positions = self.binance.get_open_positions()
                
                # 根据初始化的客户端检查黄金持仓
                if self.okx:
                    xau_positions = self.okx.get_open_positions()  # 只获取XAUT-USDT持仓
                    xau_exchange_name = "OKX"
                elif self.mt5:
                    xau_positions = self.mt5.get_open_positions()  # 只获取XAUUSD持仓
                    xau_exchange_name = "MT5"
                else:
                    xau_positions = []
                    xau_exchange_name = "未知"
                
                # 如果有持仓，分别显示持仓信息并检查平仓条件
                if xau_positions or binance_positions:
                    self._display_positions_info(binance_positions, xau_positions, xau_exchange_name, diff)
                    
                    # 检查是否要平仓（使用已获取的持仓信息，避免重复调用API）
                    should_close = self.should_close_position(diff, binance_positions, xau_positions)
                    logger.info(f'是否应该平仓: {should_close} (基于已获取持仓判断)')
                    
                    if should_close:
                        logger.info("🔄 开始执行平仓...")
                        if self.close_position(paxg_price, xauusd_price, diff):
                            logger.info("\n✅ 平仓完成")
                            # 等待10秒后计算合计盈利
                            self._calculate_total_profit_after_close()
                    else:
                        logger.info("❌ 平仓跳过: 不满足平仓条件或无实际持仓")
                
                # 如果没有持仓，检查开仓条件
                else:
                    if abs(diff) >= Config.MIN_PRICE_DIFF:
                        logger.info(f"\n🎯 满足开仓条件(|{diff:.2f}| >= {Config.MIN_PRICE_DIFF})")
                        # 这里可以启用实际开仓：
                        if self.open_position(paxg_price, xauusd_price, diff):
                            logger.info("✅ 开仓完成")

                # 简单分隔（不再打印长横线）
                time.sleep(Config.PRICE_CHECK_INTERVAL)

            except KeyboardInterrupt:
                logger.info(f"\n⌨️ 接收到中断信号，正在停止监控...")
                self.shutdown_system("用户手动停止", False)
                break
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"\n❌ 监控过程中发生错误: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"❌ 连续{consecutive_errors}次错误，系统即将关闭")
                    self.shutdown_system(f"连续{consecutive_errors}次错误: {str(e)[:100]}", True)
                    break
                    
                # 如果是严重错误，发送错误关闭通知
                if "ConnectionError" in str(e) or "APIError" in str(e):
                    logger.error("检测到严重错误，系统即将关闭...")
                    self.shutdown_system(f"系统错误: {str(e)[:100]}", True)
                    break
                time.sleep(Config.PRICE_CHECK_INTERVAL)
    
    def _check_and_notify_trading_status_change(self) -> Tuple[bool, str]:
        """检查交易状态变化并发送钉钉通知"""
        is_trading, trading_status = is_trading_time()
        
        # 如果状态发生变化，发送通知
        if self.last_trading_status is not None and self.last_trading_status != is_trading:
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            if is_trading:
                # 开盘通知
                title = "🔔 交易开盘通知"
                content = f"时间: {current_time}\n状态: {trading_status}\n系统已恢复价格监控"
                logger.info(f"📈 开盘通知: {trading_status}")
            else:
                # 闭市通知
                title = "🔕 交易闭市通知"
                content = f"时间: {current_time}\n状态: {trading_status}\n系统暂停交易，等待下次开盘"
                logger.info(f"📉 闭市通知: {trading_status}")
            
            # 发送钉钉通知
            if self.dingtalk_notifier:
                try:
                    self.dingtalk_notifier.send_simple_message_to_all(title, content)
                except Exception as e:
                    logger.warning(f"⚠️ 发送交易状态通知失败: {e}")
        
        # 更新状态
        self.last_trading_status = is_trading
        return is_trading, trading_status
    
    def _display_positions_info(self, binance_positions: List[Dict[str, Any]], 
                               xau_positions: List[Any], xau_exchange_name: str, diff: float) -> None:
        """显示持仓信息"""
        logger.info(f"\n📊 持仓状态详情:")
        logger.info("-" * 50)
        
        # 分别统计各交易所持仓
        binance_pnl = 0
        xau_pnl = 0
        
        # 显示Binance PAXG持仓
        if binance_positions:
            logger.info("🔸 Binance PAXG持仓:")
            for i, pos in enumerate(binance_positions, 1):
                try:
                    symbol = pos.get('symbol', 'N/A')
                    side = pos.get('positionSide', 'N/A')
                    size = float(pos.get('positionAmt', 0))
                    entry_price = float(pos.get('entryPrice', 0))
                    mark_price = float(pos.get('markPrice', 0))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    liquidation_price = float(pos.get('liquidationPrice', 0))
                    logger.info(f"   [{i}] {symbol} {side}: {abs(size):.4f} | 开仓价: ${entry_price:.2f} | 标记价: ${mark_price:.2f} | 盈亏: {unrealized_pnl:+.2f} | 强平价格: ${liquidation_price:.2f}")
                    binance_pnl += unrealized_pnl
                except (ValueError, TypeError) as e:
                    logger.warning(f"   [{i}] 解析Binance持仓数据失败: {e}")
            logger.info(f"   Binance小计: {binance_pnl:+.2f} USDT")
        else:
            logger.info("🔸 Binance PAXG持仓: 无")
        
        # 显示XAUUSD持仓（OKX或MT5）
        if xau_positions:
            logger.info(f"🔸 {xau_exchange_name} XAUUSD持仓:")
            for i, pos in enumerate(xau_positions, 1):
                try:
                    if self.okx:
                        # OKX持仓格式
                        inst_id = pos.get('instId', 'N/A')
                        side = pos.get('posSide', 'N/A')
                        size = float(pos.get('pos', 0))
                        avg_px = float(pos.get('avgPx', 0))
                        mark_px = float(pos.get('markPx', 0))
                        upl = float(pos.get('upl', 0))
                        upl_ratio = float(pos.get('uplRatio', 0)) * 100
                        
                        # 将张数转换为盎司显示
                        size_oz = abs(size) / 1000
                        logger.info(f"   [{i}] {inst_id} {side}: {abs(size):.0f}张({size_oz:.3f}盎司) | 开仓价: ${avg_px:.2f} | 标记价: ${mark_px:.2f} | 盈亏: {upl:+.2f} | ROE: {upl_ratio:+.2f}%")
                        xau_pnl += upl
                    elif self.mt5:
                        # MT5持仓格式
                        symbol = getattr(pos, 'symbol', 'N/A')
                        type_str = "LONG" if getattr(pos, 'type', 0) == 0 else "SHORT"
                        volume = getattr(pos, 'volume', 0)
                        price_open = getattr(pos, 'price_open', 0)
                        price_current = getattr(pos, 'price_current', 0)
                        profit = getattr(pos, 'profit', 0)
                        swap_fee = getattr(pos, 'swap', 0)
                        
                        # MT5的volume是手数，1手=100盎司
                        volume_oz = volume * 100
                        logger.info(f"   [{i}] {symbol} {type_str}: {volume}手({volume_oz}盎司) | 开仓价: ${price_open:.2f} | 当前价: ${price_current:.2f} | 盈亏: {profit:+.2f} | 隔夜费: {swap_fee:+.2f}")
                        xau_pnl += profit
                except (ValueError, TypeError, AttributeError) as e:
                    logger.warning(f"   [{i}] 解析{xau_exchange_name}持仓数据失败: {e}")
            logger.info(f"   {xau_exchange_name}小计: {xau_pnl:+.2f} USDT")
        else:
            logger.info(f"🔸 {xau_exchange_name} XAUUSD持仓: 无")
        
        # 显示总计
        total_pnl = binance_pnl + xau_pnl
        logger.info("-" * 50)
        logger.info(f"💰 总盈亏: {total_pnl:+.2f} USDT (Binance: {binance_pnl:+.2f} | {xau_exchange_name}: {xau_pnl:+.2f})")
        close_condition_met = abs(diff) <= Config.CLOSE_PRICE_DIFF
        logger.info(f'平仓条件: |{diff:.2f}| <= {Config.CLOSE_PRICE_DIFF} → {"✅满足" if close_condition_met else "❌不满足"}')
    
    @safe_execute("发送定时持仓通知")
    def _send_scheduled_position_notification(self, paxg_price: float, xauusd_price: float, diff: float) -> None:
        """发送定时持仓通知到钉钉群"""
        try:
            if not self.position_notification_enabled or not self.dingtalk_notifier:
                return
            
            # 获取当前持仓信息
            binance_positions = self.binance.get_open_positions()
            
            # 根据初始化的客户端获取黄金持仓
            if self.okx:
                xau_positions = self.okx.get_open_positions()
                xau_exchange_name = "OKX"
            elif self.mt5:
                xau_positions = self.mt5.get_open_positions()
                xau_exchange_name = "MT5"
            else:
                xau_positions = []
                xau_exchange_name = "未知"
            
            # 计算盈亏
            binance_pnl = 0
            xau_pnl = 0
            
            # 计算Binance盈亏
            if binance_positions:
                for pos in binance_positions:
                    try:
                        unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                        binance_pnl += unrealized_pnl
                    except (ValueError, TypeError):
                        pass
            
            # 计算XAUUSD交易所盈亏
            if xau_positions:
                for pos in xau_positions:
                    try:
                        if self.okx:
                            upl = float(pos.get('upl', 0))
                            xau_pnl += upl
                        elif self.mt5:
                            profit = getattr(pos, 'profit', 0)
                            xau_pnl += profit
                    except (ValueError, TypeError, AttributeError):
                        pass
            
            total_pnl = binance_pnl + xau_pnl
            
            # 构建持仓数据
            position_data = {
                'binance_positions': binance_positions,
                'xau_positions': xau_positions,
                'xau_exchange_name': xau_exchange_name,
                'current_diff': diff,
                'paxg_price': paxg_price,
                'xauusd_price': xauusd_price,
                'total_pnl': total_pnl,
                'binance_pnl': binance_pnl,
                'xau_pnl': xau_pnl,
                'timestamp': datetime.now()
            }
            
            # 发送通知
            results = self.dingtalk_notifier.send_position_notification(position_data)
            
            success_count = sum(1 for result in results.values() if result)
            total_count = len(results)
            
            logger.info(f"📱 定时持仓通知已发送: {success_count}/{total_count} 群组成功")
            
        except Exception as e:
            logger.error(f"❌ 发送定时持仓通知失败: {e}")
    
    def _check_and_send_scheduled_notification(self, paxg_price: float, xauusd_price: float, diff: float) -> None:
        """检查是否需要发送定时推送通知"""
        try:
            if not self.position_notification_enabled or not self.position_notification_times:
                return
            
            current_time = datetime.now()
            current_time_str = current_time.strftime('%H:%M')
            current_date = current_time.date()
            
            # 检查是否在推送时间点
            for notification_time in self.position_notification_times:
                try:
                    # 解析配置的时间（格式：HH:MM）
                    target_hour, target_minute = map(int, notification_time.split(':'))
                    
                    # 检查当前时间是否匹配（允许1分钟的误差）
                    if (current_time.hour == target_hour and 
                        abs(current_time.minute - target_minute) <= 1):
                        
                        # 检查今天是否已经推送过
                        if self.last_notification_date != current_date:
                            logger.info(f"⏰ 到达定时推送时间: {notification_time}")
                            self._send_scheduled_position_notification(paxg_price, xauusd_price, diff)
                            self.last_notification_date = current_date
                            break  # 一次只推送一个时间点
                            
                except ValueError as e:
                    logger.warning(f"⚠️ 解析推送时间失败: {notification_time} - {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ 检查定时推送失败: {e}")

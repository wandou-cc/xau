"""
钉钉通知模块 - 支持套利交易通知
"""
import os
import requests
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from .config import Config

# from dotenv import load_dotenv

# 加载环境变量
# load_dotenv()

logger = logging.getLogger(__name__)


class DingTalkNotifier:
    """
    钉钉通知类 - 支持多用户推送
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化钉钉通知器
        
        Args:
            config: 配置字典，如果为None则从环境变量读取
        """
        self.config = config or self._load_config_from_env()
        self.users = self._load_users_from_env()
        
        # 验证配置
        self._validate_config()
        
        logger.info(f"钉钉群组通知模块初始化完成，共配置 {len(self.users)} 个群组")
    
    def _load_config_from_env(self) -> Dict[str, Any]:
        """从环境变量加载基础配置"""
        return {
            'enabled': True,
            'secret': Config.DINGTALK_SECRET,
        }
    
    def _load_users_from_env(self) -> List[Dict[str, str]]:
        """从环境变量加载群组列表"""
        groups = []
        
        # 检查环境变量中的群组配置
        for i in range(1, 11):  # 支持最多10个群组
            group_webhook = getattr(Config, f'DINGTALK_GROUP{i}_WEBHOOK', '')
            group_name = getattr(Config, f'DINGTALK_GROUP{i}_NAME', f'群组{i}')
            
            if group_webhook:  # 只有配置了webhook的群组才会被添加
                groups.append({
                    'webhook': group_webhook,
                    'name': group_name,
                    'enabled': True
                })
                logger.info(f"加载群组配置: {group_name}")
        
        return groups
    
    def _validate_config(self) -> None:
        """验证配置参数"""
        if not self.config.get('enabled', True):
            logger.info("钉钉通知已禁用")
        
        if not self.users:
            logger.warning("未配置任何群组，通知功能将不可用")
    
    def _get_sign(self, timestamp: str, secret: str) -> str:
        """
        生成钉钉签名
        
        Args:
            timestamp: 时间戳
            secret: 密钥
            
        Returns:
            签名字符串
        """
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(
            secret.encode('utf-8'),
            string_to_sign.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return sign
    
    def _send_message(self, webhook_url: str, message: Dict[str, Any], user_name: str = "未知用户") -> bool:
        """
        发送钉钉消息
        
        Args:
            webhook_url: webhook地址
            message: 消息内容
            user_name: 用户名称
            
        Returns:
            是否发送成功
        """
        try:
            timestamp = str(round(time.time() * 1000))
            secret = self.config.get('secret', '')
            
            # 如果有密钥，生成签名
            if secret:
                sign = self._get_sign(timestamp, secret)
                webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                webhook_url,
                headers=headers,
                data=json.dumps(message),
                timeout=10
            )
            
            result = response.json()
            
            if result.get('errcode') == 0:
                logger.info(f"向用户 {user_name} 发送钉钉消息成功")
                return True
            else:
                logger.error(f"向用户 {user_name} 发送钉钉消息失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"向用户 {user_name} 发送钉钉消息异常: {str(e)}")
            return False
    
    def send_arbitrage_open_notification(self, trade_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        发送套利开仓通知
        
        Args:
            trade_data: 交易数据字典
            
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_arbitrage_open_to_group(trade_data, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def send_arbitrage_close_notification(self, trade_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        发送套利平仓通知
        
        Args:
            trade_data: 交易数据字典
            
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_arbitrage_close_to_group(trade_data, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def send_arbitrage_profit_notification(self, profit_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        发送套利盈利汇总通知
        
        Args:
            profit_data: 盈利数据字典
            
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_arbitrage_profit_to_group(profit_data, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def _send_arbitrage_open_to_group(self, trade_data: Dict[str, Any], group: Dict[str, str]) -> bool:
        """向指定群组发送开仓通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_arbitrage_open_message(trade_data)
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送开仓通知失败: {str(e)}")
            return False
    
    def _send_arbitrage_close_to_group(self, trade_data: Dict[str, Any], group: Dict[str, str]) -> bool:
        """向指定群组发送平仓通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_arbitrage_close_message(trade_data)
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送平仓通知失败: {str(e)}")
            return False
    
    def _send_arbitrage_profit_to_group(self, profit_data: Dict[str, Any], group: Dict[str, str]) -> bool:
        """向指定群组发送盈利汇总通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_arbitrage_profit_message(profit_data)
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送盈利汇总通知失败: {str(e)}")
            return False
    
    def _build_arbitrage_open_message(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建套利开仓消息"""
        trade_id = trade_data.get('trade_id', 0)
        action = trade_data.get('action', 'UNKNOWN')
        paxg_price = trade_data.get('paxg_price', 0)
        xauusd_price = trade_data.get('xauusd_price', 0)
        diff = trade_data.get('price_diff', 0)
        paxg_quantity = trade_data.get('paxg_quantity', 0)
        xau_volume = trade_data.get('xau_volume', 0)
        exchange = trade_data.get('exchange_type', 'OKX')
        timestamp = trade_data.get('timestamp', datetime.now())
        
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        content = f"""
## 🚀 套利开仓通知 #{trade_id}

### 📈 交易详情
- **时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- **策略**: {action}
- **价差**: {diff:+.2f} USDT

### 💹 价格信息
- **PAXG价格**: ${paxg_price:.2f}
- **XAUUSD价格**: ${xauusd_price:.2f}

### 📊 仓位信息
- **Binance PAXG**: {paxg_quantity:.4f} 盎司
- **{exchange} XAUUSD**: {xau_volume:.0f} {'张' if exchange == 'OKX' else '手'}

### ⚡ 执行状态
- **状态**: ✅ 开仓成功
- **交易所**: Binance + {exchange}
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"🚀 套利开仓通知 #{trade_id}",
                "text": content
            }
        }
    
    def _build_arbitrage_close_message(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建套利平仓消息"""
        paxg_price = trade_data.get('paxg_price', 0)
        xauusd_price = trade_data.get('xauusd_price', 0)
        diff = trade_data.get('price_diff', 0)
        exchange = trade_data.get('exchange_type', 'OKX')
        timestamp = trade_data.get('timestamp', datetime.now())
        
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        content = f"""
## 🔴 套利平仓通知

### 📈 交易详情
- **时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- **触发条件**: 价差回归
- **当前价差**: {diff:+.2f} USDT

### 💹 平仓价格
- **PAXG价格**: ${paxg_price:.2f}
- **XAUUSD价格**: ${xauusd_price:.2f}

### ⚡ 执行状态
- **状态**: ✅ 平仓完成
- **交易所**: Binance + {exchange}
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "🔴 套利平仓通知",
                "text": content
            }
        }
    
    def _build_arbitrage_profit_message(self, profit_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建套利盈利汇总消息"""
        total_profit = profit_data.get('total_profit', 0)
        total_trades = profit_data.get('total_trades', 0)
        binance_pnl = profit_data.get('binance_pnl', 0)
        binance_trades = profit_data.get('binance_trades', 0)
        exchange_pnl = profit_data.get('exchange_pnl', 0)
        exchange_trades = profit_data.get('exchange_trades', 0)
        exchange_name = profit_data.get('exchange_name', 'OKX')
        profit_rate = profit_data.get('profit_rate', 0)
        timestamp = profit_data.get('timestamp', datetime.now())
        
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        # 计算盈利状态emoji
        profit_emoji = "💰" if total_profit > 0 else "📉" if total_profit < 0 else "⚖️"
        
        content = f"""
## {profit_emoji} 套利交易结算报告

### 📊 交易统计
- **结算时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- **总交易数**: {total_trades}
- **总盈亏**: {total_profit:+.4f} USDT

### 💹 分交易所详情
**🏢 Binance PAXG:**
- 交易数量: {binance_trades}
- 已实现盈亏: {binance_pnl:+.4f} USDT

**🏢 {exchange_name} XAUUSD:**
- 交易数量: {exchange_trades}
- {'手续费' if exchange_name == 'OKX' else '已实现盈亏'}: {exchange_pnl:+.4f} USDT

### 📈 收益分析
- **收益率**: {profit_rate:+.4f}%
- **交易结果**: {'🎉 盈利' if total_profit > 0 else '😔 亏损' if total_profit < 0 else '🤝 平手'}
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{profit_emoji} 套利交易结算报告",
                "text": content
            }
        }
    
    def send_system_startup_notification(self) -> Dict[str, bool]:
        """
        发送系统启动通知
        
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_system_startup_to_group(group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def send_system_shutdown_notification(self, runtime_info: Dict[str, Any] = None) -> Dict[str, bool]:
        """
        发送系统关闭通知
        
        Args:
            runtime_info: 运行时信息字典
            
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_system_shutdown_to_group(runtime_info or {}, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def _send_system_startup_to_group(self, group: Dict[str, str]) -> bool:
        """向指定群组发送启动通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_system_startup_message()
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送启动通知失败: {str(e)}")
            return False
    
    def _send_system_shutdown_to_group(self, runtime_info: Dict[str, Any], group: Dict[str, str]) -> bool:
        """向指定群组发送关闭通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_system_shutdown_message(runtime_info)
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送关闭通知失败: {str(e)}")
            return False
    
    def _send_position_to_group(self, position_data: Dict[str, Any], group: Dict[str, str]) -> bool:
        """向指定群组发送持仓信息通知"""
        try:
            if not self.config.get('enabled', True):
                return False
            
            message = self._build_position_message(position_data)
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送持仓信息通知失败: {str(e)}")
            return False
    
    def _build_system_startup_message(self) -> Dict[str, Any]:
        """构建系统启动消息"""
        startup_time = datetime.now()
        
        content = f"""
## 🚀 套利交易系统启动

### ⚡ 系统状态
- **状态**: ✅ 系统已启动
- **启动时间**: {startup_time.strftime('%Y-%m-%d %H:%M:%S')}
- **运行模式**: {'测试网' if Config.USE_TESTNET else '主网'}

### 📊 交易配置
- **开仓阈值**: ±{Config.MIN_PRICE_DIFF:.2f} USDT
- **平仓阈值**: ±{Config.CLOSE_PRICE_DIFF:.2f} USDT
- **开仓数量**: {Config.PAXG_QUANTITY:.4f} 盎司
- **检查间隔**: {Config.PRICE_CHECK_INTERVAL}秒

### 🏢 交易所配置
- **主交易所**: Binance (PAXG)
- **对冲交易所**: {'OKX' if Config.USE_XAU_OKX else 'MT5'} (XAUUSD)

### 📢 系统准备就绪""".strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": "🚀 套利交易系统启动",
                "text": content
            }
        }
    
    def _build_system_shutdown_message(self, runtime_info: Dict[str, Any]) -> Dict[str, Any]:
        """构建系统关闭消息"""
        shutdown_time = datetime.now()
        start_time = runtime_info.get('start_time', shutdown_time)
        
        if isinstance(start_time, str):
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        
        # 计算运行时长
        runtime_duration = shutdown_time - start_time
        hours = int(runtime_duration.total_seconds() // 3600)
        minutes = int((runtime_duration.total_seconds() % 3600) // 60)
        seconds = int(runtime_duration.total_seconds() % 60)
        
        # 获取统计信息
        total_trades = runtime_info.get('total_trades', 0)
        total_profit = runtime_info.get('total_profit', 0)
        max_diff = runtime_info.get('max_diff', 0)
        min_diff = runtime_info.get('min_diff', 0)
        
        # 运行状态emoji
        status_emoji = "🔴" if runtime_info.get('is_error_shutdown', False) else "🛑"
        shutdown_reason = runtime_info.get('shutdown_reason', '正常关闭')
        
        content = f"""
## {status_emoji} 套利交易系统关闭

### ⏰ 运行统计
- **关闭时间**: {shutdown_time.strftime('%Y-%m-%d %H:%M:%S')}
- **运行时长**: {hours}小时 {minutes}分钟 {seconds}秒
- **关闭原因**: {shutdown_reason}

### 📊 交易统计
- **总交易次数**: {total_trades}
- **累计盈亏**: {total_profit:+.4f} USDT
- **价差区间**: [{min_diff:.2f}, {max_diff:.2f}] USDT

### 📈 运行状态
- **系统状态**: {'❌ 异常退出' if runtime_info.get('is_error_shutdown', False) else '✅ 正常关闭'}
- **数据保存**: ✅ 交易记录已保存

### 💡 下次启动
系统已安全关闭，可随时重新启动继续套利交易。
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{status_emoji} 套利交易系统关闭",
                "text": content
            }
        }
    
    def _build_position_message(self, position_data: Dict[str, Any]) -> Dict[str, Any]:
        """构建持仓信息消息"""
        timestamp = position_data.get('timestamp', datetime.now())
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        binance_positions = position_data.get('binance_positions', [])
        xau_positions = position_data.get('xau_positions', [])
        xau_exchange_name = position_data.get('xau_exchange_name', 'OKX')
        current_diff = position_data.get('current_diff', 0)
        paxg_price = position_data.get('paxg_price', 0)
        xauusd_price = position_data.get('xauusd_price', 0)
        total_pnl = position_data.get('total_pnl', 0)
        binance_pnl = position_data.get('binance_pnl', 0)
        xau_pnl = position_data.get('xau_pnl', 0)
        
        # 状态emoji
        if binance_positions or xau_positions:
            status_emoji = "📊"
            position_status = "有持仓"
        else:
            status_emoji = "💤"
            position_status = "无持仓"
        
        content = f"""
## {status_emoji} 持仓状态报告

### ⏰ 基本信息
- **时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}
- **状态**: {position_status}
- **当前价差**: {current_diff:+.2f} USDT

### 💹 价格信息
- **PAXG价格**: ${paxg_price:.2f}
- **XAUUSD价格**: ${xauusd_price:.2f}

### 📊 持仓详情"""
        
        # Binance持仓信息
        if binance_positions:
            content += f"\n**🏢 Binance PAXG持仓:**\n"
            for i, pos in enumerate(binance_positions, 1):
                try:
                    symbol = pos.get('symbol', 'N/A')
                    side = pos.get('positionSide', 'N/A')
                    size = float(pos.get('positionAmt', 0))
                    entry_price = float(pos.get('entryPrice', 0))
                    mark_price = float(pos.get('markPrice', 0))
                    unrealized_pnl = float(pos.get('unRealizedProfit', 0))
                    
                    content += f"- [{i}] {symbol} {side}: {abs(size):.4f} | 开仓: ${entry_price:.2f} | 标记: ${mark_price:.2f} | 盈亏: {unrealized_pnl:+.2f}\n"
                except (ValueError, TypeError):
                    content += f"- [{i}] 解析持仓数据失败\n"
        else:
            content += f"\n**🏢 Binance PAXG持仓:** 无\n"
        
        # XAUUSD持仓信息
        if xau_positions:
            content += f"\n**🏢 {xau_exchange_name} XAUUSD持仓:**\n"
            for i, pos in enumerate(xau_positions, 1):
                try:
                    if xau_exchange_name == "OKX":
                        inst_id = pos.get('instId', 'N/A')
                        side = pos.get('posSide', 'N/A')
                        size = float(pos.get('pos', 0))
                        avg_px = float(pos.get('avgPx', 0))
                        mark_px = float(pos.get('markPx', 0))
                        upl = float(pos.get('upl', 0))
                        
                        size_oz = abs(size) / 1000
                        content += f"- [{i}] {inst_id} {side}: {abs(size):.0f}张({size_oz:.3f}盎司) | 开仓: ${avg_px:.2f} | 标记: ${mark_px:.2f} | 盈亏: {upl:+.2f}\n"
                    else:  # MT5
                        symbol = getattr(pos, 'symbol', 'N/A')
                        type_str = "LONG" if getattr(pos, 'type', 0) == 0 else "SHORT"
                        volume = getattr(pos, 'volume', 0)
                        price_open = getattr(pos, 'price_open', 0)
                        price_current = getattr(pos, 'price_current', 0)
                        profit = getattr(pos, 'profit', 0)
                        
                        volume_oz = volume * 100
                        content += f"- [{i}] {symbol} {type_str}: {volume}手({volume_oz}盎司) | 开仓: ${price_open:.2f} | 当前: ${price_current:.2f} | 盈亏: {profit:+.2f}\n"
                except (ValueError, TypeError, AttributeError):
                    content += f"- [{i}] 解析{xau_exchange_name}持仓数据失败\n"
        else:
            content += f"\n**🏢 {xau_exchange_name} XAUUSD持仓:** 无\n"
        
        # 总盈亏
        content += f"""
### 💰 盈亏汇总
- **Binance盈亏**: {binance_pnl:+.2f} USDT
- **{xau_exchange_name}盈亏**: {xau_pnl:+.2f} USDT
- **总盈亏**: {total_pnl:+.2f} USDT

### 📈 状态分析
- **盈亏状态**: {'🟢 盈利' if total_pnl > 0 else '🔴 亏损' if total_pnl < 0 else '⚪ 平衡'}
- **价差状态**: {'⬆️ PAXG高' if current_diff > 0 else '⬇️ PAXG低' if current_diff < 0 else '⚖️ 平衡'}
        """.strip()
        
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{status_emoji} 持仓状态报告",
                "text": content
            }
        }
    
    def send_simple_message_to_all(self, title: str, content: str) -> Dict[str, bool]:
        """
        向所有群组发送简单消息
        
        Args:
            title: 消息标题
            content: 消息内容
            
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self.send_simple_message_to_group(title, content, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def send_position_notification(self, position_data: Dict[str, Any]) -> Dict[str, bool]:
        """
        发送持仓信息通知
        
        Args:
            position_data: 持仓数据字典，包含以下字段：
                - binance_positions: Binance持仓列表
                - xau_positions: XAUUSD持仓列表
                - xau_exchange_name: XAUUSD交易所名称
                - current_diff: 当前价差
                - paxg_price: PAXG价格
                - xauusd_price: XAUUSD价格
                - total_pnl: 总盈亏
                - binance_pnl: Binance盈亏
                - xau_pnl: XAUUSD交易所盈亏
                - timestamp: 时间戳
                
        Returns:
            每个群组的发送结果字典
        """
        results = {}
        
        for group in self.users:
            if group.get('enabled', True):
                success = self._send_position_to_group(position_data, group)
                results[group['name']] = success
            else:
                results[group['name']] = False
                logger.debug(f"群组 {group['name']} 已禁用，跳过通知")
        
        return results
    
    def send_simple_message_to_group(self, title: str, content: str, group: Dict[str, str]) -> bool:
        """
        向指定群组发送简单消息
        
        Args:
            title: 消息标题
            content: 消息内容
            group: 群组信息
            
        Returns:
            是否发送成功
        """
        try:
            if not self.config.get('enabled', True):
                logger.debug("钉钉通知已禁用")
                return False
            
            message = {
                "msgtype": "text",
                "text": {
                    "content": f"{title}\n\n{content}"
                }
            }
            
            return self._send_message(group['webhook'], message, group['name'])
                
        except Exception as e:
            logger.error(f"向群组 {group['name']} 发送简单消息失败: {str(e)}")
            return False
    
    def add_group(self, webhook_url: str, group_name: str) -> bool:
        """
        添加新群组
        
        Args:
            webhook_url: 群组webhook地址
            group_name: 群组名称
            
        Returns:
            是否添加成功
        """
        try:
            # 检查群组是否已存在
            for group in self.users:
                if group['webhook'] == webhook_url:
                    logger.warning(f"群组 {group_name} 已存在")
                    return False
            
            # 添加新群组
            new_group = {
                'webhook': webhook_url,
                'name': group_name,
                'enabled': True
            }
            self.users.append(new_group)
            
            logger.info(f"成功添加群组: {group_name}")
            return True
            
        except Exception as e:
            logger.error(f"添加群组失败: {str(e)}")
            return False
    
    def remove_group(self, webhook_url: str) -> bool:
        """
        移除群组
        
        Args:
            webhook_url: 群组webhook地址
            
        Returns:
            是否移除成功
        """
        try:
            for i, group in enumerate(self.users):
                if group['webhook'] == webhook_url:
                    removed_group = self.users.pop(i)
                    logger.info(f"成功移除群组: {removed_group['name']}")
                    return True
            
            logger.warning(f"未找到webhook: {webhook_url}")
            return False
            
        except Exception as e:
            logger.error(f"移除群组失败: {str(e)}")
            return False
    
    def enable_group(self, webhook_url: str) -> bool:
        """
        启用群组
        
        Args:
            webhook_url: 群组webhook地址
            
        Returns:
            是否启用成功
        """
        try:
            for group in self.users:
                if group['webhook'] == webhook_url:
                    group['enabled'] = True
                    logger.info(f"成功启用群组: {group['name']}")
                    return True
            
            logger.warning(f"未找到webhook: {webhook_url}")
            return False
            
        except Exception as e:
            logger.error(f"启用群组失败: {str(e)}")
            return False
    
    def disable_group(self, webhook_url: str) -> bool:
        """
        禁用群组
        
        Args:
            webhook_url: 群组webhook地址
            
        Returns:
            是否禁用成功
        """
        try:
            for group in self.users:
                if group['webhook'] == webhook_url:
                    group['enabled'] = False
                    logger.info(f"成功禁用群组: {group['name']}")
                    return True
            
            logger.warning(f"未找到webhook: {webhook_url}")
            return False
            
        except Exception as e:
            logger.error(f"禁用群组失败: {str(e)}")
            return False
    
    def get_groups_info(self) -> List[Dict[str, Any]]:
        """
        获取群组信息列表
        
        Returns:
            群组信息列表
        """
        return [
            {
                'webhook': group['webhook'][:50] + '...' if len(group['webhook']) > 50 else group['webhook'],
                'name': group['name'],
                'enabled': group.get('enabled', True)
            }
            for group in self.users
        ]
    
    def test_connection(self) -> Dict[str, bool]:
        """
        测试钉钉连接
        
        Returns:
            连接测试结果字典
        """
        results = {}
        
        try:
            logger.info("开始测试钉钉连接...")
            
            # 测试向每个群组发送消息
            for group in self.users:
                if group.get('enabled', True):
                    success = self.send_simple_message_to_group(
                        "连接测试", 
                        f"这是一条测试消息，发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                        group
                    )
                    results[group['name']] = success
                else:
                    results[group['name']] = False
                    logger.debug(f"群组 {group['name']} 已禁用，跳过测试")
            
            if results:
                logger.info("钉钉连接测试完成")
            else:
                logger.warning("未配置任何群组")
                
        except Exception as e:
            logger.error(f"钉钉连接测试异常: {str(e)}")
        
        return results 
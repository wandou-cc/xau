"""
黄金 XAU/USD 交易时间管理模块

基于 MT5 欧洲时间 (EEST/EET) 的交易时间对照表：
- 开盘：周一 01:01 EEST (北京时间周一 06:01，夏令时期间)
- 收盘：周五 23:58 EEST (北京时间周六 04:58，夏令时期间)
- 每日休市：23:58 - 次日 01:01 EEST (北京时间 04:58 - 06:01，夏令时期间)

注意：EEST 是欧洲东部夏令时，比 EET 快1小时
- 夏令时期间 (3月-10月): 使用 EEST (UTC+3)
- 标准时间期间 (10月-3月): 使用 EET (UTC+2)

支持多时区部署：
- 自动检测服务器时区
- 支持日本、新加坡、美国等不同时区的服务器部署
- 使用服务器本地时间进行校验
- 自动处理夏令时变化
"""
import time
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict
import pytz

logger = logging.getLogger(__name__)

class TradingTimeManager:
    """黄金交易时间管理器"""
    
    def __init__(self):
        """初始化交易时间管理器"""
        # 定义时区
        self.eet_tz = pytz.timezone('Europe/Athens')  # 欧洲东部时间 (EET/EEST)
        self.beijing_tz = pytz.timezone('Asia/Shanghai')  # 北京时间
        self.et_tz = pytz.timezone('US/Eastern')  # 美国东部时间
        self.japan_tz = pytz.timezone('Asia/Tokyo')  # 日本时间
        self.singapore_tz = pytz.timezone('Asia/Singapore')  # 新加坡时间
        
        # 自动检测服务器时区
        self.server_tz = self._detect_server_timezone()
        
        # 交易时间配置 (基于欧洲时间)
        self.weekly_open_time = {
            'day': 0,  # 周一 (0=Monday)
            'hour': 1,
            'minute': 1
        }
        
        self.weekly_close_time = {
            'day': 4,  # 周五 (4=Friday)
            'hour': 23,
            'minute': 58
        }
        
        self.daily_close_time = {
            'hour': 23,
            'minute': 58
        }
        
        self.daily_open_time = {
            'hour': 1,
            'minute': 1
        }
        
        logger.info("🕐 黄金交易时间管理器初始化完成")
        self._log_current_time_info()
        self._validate_server_time()
    
    def _detect_server_timezone(self) -> pytz.timezone:
        """自动检测服务器时区"""
        try:
            # 方法1: 从环境变量获取
            tz_env = os.environ.get('TZ')
            if tz_env:
                try:
                    detected_tz = pytz.timezone(tz_env)
                    logger.info(f"🌍 从环境变量检测到时区: {tz_env}")
                    return detected_tz
                except Exception:
                    logger.warning(f"⚠️ 环境变量TZ值无效: {tz_env}")
            
            # 方法2: 从系统时间获取
            local_tz = datetime.now().astimezone().tzinfo
            if hasattr(local_tz, 'zone'):
                try:
                    detected_tz = pytz.timezone(local_tz.zone)
                    logger.info(f"🌍 从系统时间检测到时区: {local_tz.zone}")
                    return detected_tz
                except Exception:
                    logger.warning(f"⚠️ 系统时区无效: {local_tz.zone}")
            
            # 方法3: 根据UTC偏移量推断常见时区
            utc_offset = datetime.now().astimezone().utcoffset()
            offset_hours = utc_offset.total_seconds() / 3600
            
            # 常见时区映射
            timezone_mapping = {
                9: 'Asia/Tokyo',      # 日本
                8: 'Asia/Shanghai',   # 中国/新加坡
                7: 'Asia/Bangkok',    # 泰国
                -5: 'US/Eastern',     # 美国东部
                -8: 'US/Pacific',     # 美国西部
                0: 'UTC',             # UTC
                1: 'Europe/Berlin',   # 德国
                2: 'Europe/Athens',   # 希腊
            }
            
            if offset_hours in timezone_mapping:
                detected_tz = pytz.timezone(timezone_mapping[offset_hours])
                logger.info(f"🌍 根据UTC偏移量推断时区: {timezone_mapping[offset_hours]} (UTC{offset_hours:+.0f})")
                return detected_tz
            
            # 默认使用UTC
            logger.warning("⚠️ 无法检测服务器时区，使用UTC作为默认时区")
            return pytz.UTC
            
        except Exception as e:
            logger.error(f"❌ 时区检测失败: {e}")
            return pytz.UTC
    
    def _validate_server_time(self) -> None:
        """验证服务器时间是否准确"""
        try:
            server_time = datetime.now(self.server_tz)
            eet_time = datetime.now(self.eet_tz)
            
            # 计算时差
            time_diff = (server_time.utcoffset() - eet_time.utcoffset()).total_seconds() / 3600
            
            logger.info(f"🕐 服务器时间校验:")
            logger.info(f"   服务器时区: {self.server_tz.zone}")
            logger.info(f"   服务器时间: {server_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   欧洲时间: {eet_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   时差: {time_diff:+.1f}小时")
            
            # 检查时间差异是否合理
            if abs(time_diff) > 12:
                logger.warning(f"⚠️ 服务器时间与欧洲时间差异较大: {time_diff:+.1f}小时")
                logger.warning("   请检查服务器时间设置是否正确")
            else:
                logger.info("✅ 服务器时间校验通过")
                
        except Exception as e:
            logger.error(f"❌ 服务器时间校验失败: {e}")
    
    def _log_current_time_info(self) -> None:
        """记录当前时间信息"""
        try:
            now_eet = datetime.now(self.eet_tz)
            now_beijing = datetime.now(self.beijing_tz)
            now_et = datetime.now(self.et_tz)
            now_server = datetime.now(self.server_tz)
            now_japan = datetime.now(self.japan_tz)
            now_singapore = datetime.now(self.singapore_tz)
            
            # 判断当前是夏令时还是标准时间
            is_dst = now_eet.dst() != timedelta(0)
            europe_timezone_name = "EEST" if is_dst else "EET"
            
            logger.info(f"🕐 当前时间信息:")
            logger.info(f"   服务器时间 ({self.server_tz.zone}): {now_server.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   欧洲时间 ({europe_timezone_name}): {now_eet.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   北京时间 (CST): {now_beijing.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   日本时间 (JST): {now_japan.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   新加坡时间 (SGT): {now_singapore.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            logger.info(f"   美国东部时间 (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            # 显示夏令时状态
            if is_dst:
                logger.info(f"   📅 当前为夏令时期间，使用 EEST (UTC+3)")
            else:
                logger.info(f"   📅 当前为标准时间期间，使用 EET (UTC+2)")
                
        except Exception as e:
            logger.warning(f"⚠️ 获取时间信息失败: {e}")
    
    def get_current_eet_time(self) -> datetime:
        """获取当前欧洲东部时间"""
        return datetime.now(self.eet_tz)
    
    def get_current_beijing_time(self) -> datetime:
        """获取当前北京时间"""
        return datetime.now(self.beijing_tz)
    
    def get_current_et_time(self) -> datetime:
        """获取当前美国东部时间"""
        return datetime.now(self.et_tz)
    
    def get_current_server_time(self) -> datetime:
        """获取当前服务器时间"""
        return datetime.now(self.server_tz)
    
    def get_current_japan_time(self) -> datetime:
        """获取当前日本时间"""
        return datetime.now(self.japan_tz)
    
    def get_current_singapore_time(self) -> datetime:
        """获取当前新加坡时间"""
        return datetime.now(self.singapore_tz)
    
    def is_trading_time(self) -> Tuple[bool, str]:
        """
        检查当前是否为交易时间
        
        Returns:
            Tuple[bool, str]: (是否在交易时间, 状态描述)
        """
        try:
            now_eet = self.get_current_eet_time()
            weekday = now_eet.weekday()  # 0=Monday, 6=Sunday
            current_time = now_eet.time()
            
            # 判断当前是夏令时还是标准时间
            is_dst = now_eet.dst() != timedelta(0)
            timezone_suffix = "EEST" if is_dst else "EET"
            
            # 检查是否在周一到周五之间
            if weekday < 5:  # 周一到周五
                # 检查是否在每日交易时间内 (01:01 - 23:58)
                daily_open = datetime.strptime("01:01", "%H:%M").time()
                daily_close = datetime.strptime("23:58", "%H:%M").time()
                
                if daily_open <= current_time <= daily_close:
                    return True, f"交易时间 - {now_eet.strftime('%A %H:%M:%S')} {timezone_suffix}"
                else:
                    return False, f"每日休市时间 - {now_eet.strftime('%A %H:%M:%S')} {timezone_suffix}"
            else:
                # 周末
                return False, f"周末休市 - {now_eet.strftime('%A %H:%M:%S')} {timezone_suffix}"
                
        except Exception as e:
            logger.error(f"❌ 检查交易时间失败: {e}")
            return False, f"时间检查错误: {e}"
    
    def get_next_trading_time(self) -> Tuple[Optional[datetime], str]:
        """
        获取下次交易开始时间
        
        Returns:
            Tuple[Optional[datetime], str]: (下次交易时间, 描述)
        """
        try:
            now_eet = self.get_current_eet_time()
            weekday = now_eet.weekday()
            current_time = now_eet.time()
            
            # 如果当前是交易时间，返回当前时间
            is_trading, _ = self.is_trading_time()
            if is_trading:
                return now_eet, "当前正在交易时间"
            
            # 计算下次交易时间
            if weekday < 5:  # 周一到周五
                # 如果在每日休市时间 (23:58 - 01:01)
                daily_close = datetime.strptime("23:58", "%H:%M").time()
                daily_open = datetime.strptime("01:01", "%H:%M").time()
                
                if current_time > daily_close:
                    # 今日已收盘，下次交易是明天 01:01
                    next_trading = now_eet.replace(hour=1, minute=1, second=0, microsecond=0) + timedelta(days=1)
                elif current_time < daily_open:
                    # 今日未开盘，下次交易是今天 01:01
                    next_trading = now_eet.replace(hour=1, minute=1, second=0, microsecond=0)
                else:
                    # 这种情况理论上不会发生，因为已经在交易时间检查中处理了
                    next_trading = now_eet.replace(hour=1, minute=1, second=0, microsecond=0)
            else:
                # 周末，下次交易是下周一 01:01
                days_until_monday = (7 - weekday) % 7
                if days_until_monday == 0:  # 如果今天是周日
                    days_until_monday = 1
                next_trading = now_eet.replace(hour=1, minute=1, second=0, microsecond=0) + timedelta(days=days_until_monday)
            
            # 判断下次交易时间是夏令时还是标准时间
            is_dst = next_trading.dst() != timedelta(0)
            timezone_suffix = "EEST" if is_dst else "EET"
            return next_trading, f"下次交易时间: {next_trading.strftime('%A %H:%M:%S')} {timezone_suffix}"
            
        except Exception as e:
            logger.error(f"❌ 计算下次交易时间失败: {e}")
            return None, f"计算失败: {e}"
    
    def get_time_until_next_trading(self) -> Tuple[Optional[timedelta], str]:
        """
        获取距离下次交易开始的时间
        
        Returns:
            Tuple[Optional[timedelta], str]: (时间差, 描述)
        """
        try:
            next_trading, description = self.get_next_trading_time()
            if next_trading is None:
                return None, description
            
            now_eet = self.get_current_eet_time()
            time_diff = next_trading - now_eet
            
            # 格式化时间差
            total_seconds = int(time_diff.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            
            if hours > 0:
                time_str = f"{hours}小时{minutes}分钟"
            elif minutes > 0:
                time_str = f"{minutes}分钟{seconds}秒"
            else:
                time_str = f"{seconds}秒"
            
            return time_diff, f"距离下次交易: {time_str}"
            
        except Exception as e:
            logger.error(f"❌ 计算距离下次交易时间失败: {e}")
            return None, f"计算失败: {e}"
    
    def wait_until_trading_time(self, check_interval: int = 60) -> None:
        """
        等待直到交易时间开始
        
        Args:
            check_interval: 检查间隔（秒）
        """
        logger.info("⏳ 当前不在交易时间，等待交易开始...")
        
        while True:
            try:
                is_trading, status = self.is_trading_time()
                
                if is_trading:
                    logger.info(f"✅ 交易时间开始: {status}")
                    break
                
                # 获取下次交易时间和倒计时
                time_diff, countdown = self.get_time_until_next_trading()
                
                if time_diff:
                    # 显示倒计时
                    total_seconds = int(time_diff.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    if hours > 0:
                        countdown_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        countdown_str = f"{minutes:02d}:{seconds:02d}"
                    
                    print(f"\r⏰ {status} | 倒计时: {countdown_str}", end="", flush=True)
                
                time.sleep(check_interval)
                
            except KeyboardInterrupt:
                logger.info("\n⌨️ 用户中断等待")
                break
            except Exception as e:
                logger.error(f"❌ 等待交易时间时发生错误: {e}")
                time.sleep(check_interval)
    
    def get_trading_schedule_info(self) -> str:
        """
        获取交易时间表信息
        
        Returns:
            str: 格式化的交易时间表
        """
        try:
            now_eet = self.get_current_eet_time()
            now_beijing = self.get_current_beijing_time()
            now_et = self.get_current_et_time()
            now_server = self.get_current_server_time()
            now_japan = self.get_current_japan_time()
            now_singapore = self.get_current_singapore_time()
            
            # 判断当前是夏令时还是标准时间
            is_dst = now_eet.dst() != timedelta(0)
            current_timezone = "EEST" if is_dst else "EET"
            
            # 计算与北京时间的时差
            beijing_offset = 8  # 北京时间固定为UTC+8
            europe_offset = 3 if is_dst else 2  # EEST=UTC+3, EET=UTC+2
            time_diff_with_beijing = europe_offset - beijing_offset
            
            info = f"""
🕐 黄金 XAU/USD 交易时间表 (基于 MT5 欧洲时间)

📅 交易时间:
   开盘: 周一 01:01 {current_timezone} (北京时间周一 {7 + time_diff_with_beijing:02d}:01)
   收盘: 周五 23:58 {current_timezone} (北京时间周六 {5 + time_diff_with_beijing:02d}:58)
   每日休市: 23:58 - 次日 01:01 {current_timezone} (北京时间 {5 + time_diff_with_beijing:02d}:58 - {7 + time_diff_with_beijing:02d}:01)

🕐 当前时间:
   服务器时间 ({self.server_tz.zone}): {now_server.strftime('%Y-%m-%d %H:%M:%S %Z')}
   欧洲时间 ({current_timezone}): {now_eet.strftime('%Y-%m-%d %H:%M:%S %Z')}
   北京时间 (CST): {now_beijing.strftime('%Y-%m-%d %H:%M:%S %Z')}
   日本时间 (JST): {now_japan.strftime('%Y-%m-%d %H:%M:%S %Z')}
   新加坡时间 (SGT): {now_singapore.strftime('%Y-%m-%d %H:%M:%S %Z')}
   美国东部时间 (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}

📊 交易状态: {self.is_trading_time()[1]}
"""
            
            next_trading, next_desc = self.get_next_trading_time()
            if next_trading:
                info += f"⏰ {next_desc}\n"
            
            time_diff, countdown = self.get_time_until_next_trading()
            if time_diff:
                info += f"⏳ {countdown}\n"
            
            return info
            
        except Exception as e:
            logger.error(f"❌ 获取交易时间表信息失败: {e}")
            return f"获取交易时间表信息失败: {e}"
    
    def is_weekend(self) -> bool:
        """检查当前是否为周末"""
        try:
            now_eet = self.get_current_eet_time()
            return now_eet.weekday() >= 5  # 5=Saturday, 6=Sunday
        except Exception as e:
            logger.error(f"❌ 检查周末状态失败: {e}")
            return False
    
    def is_daily_break(self) -> bool:
        """检查当前是否为每日休市时间"""
        try:
            now_eet = self.get_current_eet_time()
            current_time = now_eet.time()
            
            # 每日休市时间: 23:58 - 01:01
            daily_close = datetime.strptime("23:58", "%H:%M").time()
            daily_open = datetime.strptime("01:01", "%H:%M").time()
            
            return current_time > daily_close or current_time < daily_open
        except Exception as e:
            logger.error(f"❌ 检查每日休市时间失败: {e}")
            return False
    
    def get_timezone_status(self) -> Dict[str, str]:
        """
        获取当前时区状态信息
        
        Returns:
            Dict[str, str]: 时区状态信息
        """
        try:
            now_eet = self.get_current_eet_time()
            is_dst = now_eet.dst() != timedelta(0)
            
            return {
                'current_timezone': "EEST" if is_dst else "EET",
                'is_dst': str(is_dst),
                'utc_offset': "+3" if is_dst else "+2",
                'description': "夏令时期间" if is_dst else "标准时间期间",
                'beijing_time_diff': "-5" if is_dst else "-6"  # 与北京时间的时差
            }
        except Exception as e:
            logger.error(f"❌ 获取时区状态失败: {e}")
            return {'error': str(e)}
    
    def get_deployment_info(self) -> Dict[str, str]:
        """
        获取部署信息
        
        Returns:
            Dict[str, str]: 部署相关信息
        """
        try:
            server_time = self.get_current_server_time()
            eet_time = self.get_current_eet_time()
            
            # 计算时差
            time_diff = (server_time.utcoffset() - eet_time.utcoffset()).total_seconds() / 3600
            
            # 判断部署地区
            deployment_region = "未知"
            if self.server_tz.zone == 'Asia/Tokyo':
                deployment_region = "日本"
            elif self.server_tz.zone == 'Asia/Singapore':
                deployment_region = "新加坡"
            elif self.server_tz.zone == 'Asia/Shanghai':
                deployment_region = "中国"
            elif self.server_tz.zone == 'US/Eastern' or self.server_tz.zone == 'US/Pacific':
                deployment_region = "美国"
            elif self.server_tz.zone == 'Europe/Athens' or self.server_tz.zone == 'Europe/Berlin':
                deployment_region = "欧洲"
            elif self.server_tz.zone == 'UTC':
                deployment_region = "UTC"
            
            return {
                'server_timezone': self.server_tz.zone,
                'deployment_region': deployment_region,
                'server_time': server_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'eet_time': eet_time.strftime('%Y-%m-%d %H:%M:%S %Z'),
                'time_difference': f"{time_diff:+.1f}小时",
                'is_trading_time': str(self.is_trading_time()[0])
            }
            
        except Exception as e:
            logger.error(f"❌ 获取部署信息失败: {e}")
            return {'error': str(e)}


# 全局实例
trading_time_manager = TradingTimeManager()


def is_trading_time() -> Tuple[bool, str]:
    """检查当前是否为交易时间的便捷函数"""
    return trading_time_manager.is_trading_time()


def wait_until_trading_time(check_interval: int = 60) -> None:
    """等待直到交易时间开始的便捷函数"""
    trading_time_manager.wait_until_trading_time(check_interval)


def get_trading_schedule_info() -> str:
    """获取交易时间表信息的便捷函数"""
    return trading_time_manager.get_trading_schedule_info()


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    print("🧪 测试黄金交易时间模块")
    print("=" * 50)
    
    # 显示部署信息
    print("\n🌍 部署信息:")
    deployment_info = trading_time_manager.get_deployment_info()
    for key, value in deployment_info.items():
        print(f"   {key}: {value}")
    
    # 显示交易时间表
    print(get_trading_schedule_info())
    
    # 测试交易时间检查
    is_trading, status = is_trading_time()
    print(f"当前交易状态: {status}")
    
    if not is_trading:
        print("\n⏳ 当前不在交易时间，开始等待...")
        print("按 Ctrl+C 停止等待")
        try:
            wait_until_trading_time(10)  # 每10秒检查一次
        except KeyboardInterrupt:
            print("\n⌨️ 用户停止等待")
    else:
        print("✅ 当前在交易时间内")

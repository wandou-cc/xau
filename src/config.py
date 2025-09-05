import os
from dotenv import load_dotenv, find_dotenv
import urllib3
import warnings

# 忽略SSL警告
urllib3.disable_warnings()
warnings.filterwarnings('ignore', category=urllib3.exceptions.NotOpenSSLWarning)

# 先加载.env（支持相对路径与父级目录）
_ = load_dotenv(find_dotenv())

class Config:

    # 统一控制测试网/主网   
    USE_TESTNET = os.getenv('USE_TESTNET', 'true').lower() == 'true'  

    # 代理配置
    USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'  # 是否使用代理
    PROXY_URL = os.getenv('PROXY_URL', '')  # 代理URL，默认为空

    # 是否使用OKX的XAUUSD
    USE_XAU_OKX = os.getenv('USE_XAU_OKX', 'false').lower() == 'true' 

    if USE_TESTNET:
        # 测试网配置
        BINANCE_API_KEY = os.getenv('BINANCE_TEST_API_KEY')
        BINANCE_API_SECRET = os.getenv('BINANCE_TEST_API_SECRET')
        OKX_API_KEY = os.getenv('OKX_TEST_API_KEY')
        OKX_API_SECRET = os.getenv('OKX_TEST_API_SECRET')
        OKX_PASSPHRASE = os.getenv('OKX_TEST_PASSPHRASE')
    else:
        # 主网配置
        BINANCE_API_KEY = os.getenv('BINANCE_API_KEY')
        BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET')
        OKX_API_KEY = os.getenv('OKX_API_KEY')
        OKX_API_SECRET = os.getenv('OKX_API_SECRET')
        OKX_PASSPHRASE = os.getenv('OKX_PASSPHRASE')


    # 时间间隔
    PRICE_CHECK_INTERVAL = int(os.getenv('PRICE_CHECK_INTERVAL', 10)) 

    # 交易时间校验配置
    ENABLE_TRADING_TIME_CHECK = os.getenv('ENABLE_TRADING_TIME_CHECK', 'true').lower() == 'true'  # 是否启用交易时间校验

    # 交易配置  
    MIN_PRICE_DIFF = float(os.getenv('MIN_PRICE_DIFF', 6))  # 开仓阈值
    CLOSE_PRICE_DIFF = float(os.getenv('CLOSE_PRICE_DIFF', 2))  # 平仓阈值
    OPEN_LEVEL = float(os.getenv('OPEN_LEVEL', 1))  # 开仓杠杆
    PAXG_QUANTITY = float(os.getenv('PAXG_QUANTITY', 0.01))  # 开仓PAXG数量

    # 文件配置
    TRADE_LOG_FILE = os.getenv('TRADE_LOG_FILE', 'trades.log')
    DIFF_STATS_FILE = os.getenv('DIFF_STATS_FILE', 'price_diff_stats.log')

    # 交易对配置
    PAXG_SYMBOL = 'PAXGUSDT'
    XAUUSD_SYMBOL = 'XAUUSD+'  # MT5中的黄金交易对
    OKX_XAUUSD_SYMBOL = 'XAUT-USDT-SWAP'  # OKX中的黄金交易对


    # 钉钉通知配置
    USE_DINGTALK = os.getenv('USE_DINGTALK', 'true').lower() == 'true'
    DINGTALK_SECRET = os.getenv('DINGTALK_SECRET')
    
    # 支持多个钉钉群组配置
    DINGTALK_GROUP1_WEBHOOK = os.getenv('DINGTALK_GROUP1_WEBHOOK')
    DINGTALK_GROUP1_NAME = os.getenv('DINGTALK_GROUP1_NAME', '套利交易群1')

    # 定时推送持仓信息配置
    ENABLE_POSITION_NOTIFICATION = os.getenv('ENABLE_POSITION_NOTIFICATION', 'true').lower() == 'true'
    # 推送时间配置数组（24小时制，格式：HH:MM）
    POSITION_NOTIFICATION_TIMES = [
        time.strip() for time in os.getenv('POSITION_NOTIFICATION_TIMES', '09:00,12:00,15:00,18:00,21:00').split(',')
        if time.strip()
    ]


 
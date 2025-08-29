from src.arbitrage.arbitrage_manager import ArbitrageManager
import atexit
import signal
import sys

def main():
    arbitrage_manager = None
    
    def signal_handler(signum, frame):
        """处理信号退出"""
        if arbitrage_manager:
            signal_name = "SIGINT" if signum == signal.SIGINT else f"SIGNAL-{signum}"
            arbitrage_manager.shutdown_system(f"接收到{signal_name}信号", False)
        sys.exit(0)
    
    def exit_handler():
        """程序退出时处理"""
        if arbitrage_manager and not getattr(arbitrage_manager, '_shutdown_called', False):
            arbitrage_manager.shutdown_system("程序正常退出", False)
            arbitrage_manager._shutdown_called = True
    
    try:
        # 注册信号处理器和退出处理器
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        atexit.register(exit_handler)
        
        # 初始化套利管理器
        arbitrage_manager = ArbitrageManager()
        
        # 开始监控价格
        arbitrage_manager.monitor_prices()
        
    except KeyboardInterrupt:
        print("\n⌨️ 程序被用户中断")
        if arbitrage_manager:
            arbitrage_manager.shutdown_system("用户键盘中断", False)
    except Exception as e:
        print(f"❌ 程序发生错误: {e}")
        if arbitrage_manager:
            arbitrage_manager.shutdown_system(f"程序异常: {str(e)[:100]}", True)
        raise

if __name__ == "__main__":
    main()
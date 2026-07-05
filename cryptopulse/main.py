"""
CryptoPulse — 主入口

启动数据管道，连接 OKX WebSocket 获取实时数据。

Usage:
    python main.py --symbol BTC-USDT --style short_term
"""

from __future__ import annotations

import argparse
import asyncio
import os
import signal

from loguru import logger

from cryptopulse.config import settings
from cryptopulse.config import LOG_DIR
from cryptopulse.core.data.pipeline import DataPipeline
from cryptopulse.core.indicators.engine import TechnicalSignalEngine
from cryptopulse.core.output.formatter import format_signal


def setup_proxy() -> None:
    """如果配置了代理，设置 HTTP_PROXY / HTTPS_PROXY 环境变量。
    requests 和 websockets 库会自动读取这些变量。
    """
    proxy = settings.proxy
    if proxy:
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["WS_PROXY"] = proxy
        os.environ["WSS_PROXY"] = proxy
        logger.info(f"代理已配置: {proxy}")
    else:
        logger.info("未配置代理（直连）")


def setup_logging():
    """配置 loguru"""
    import sys
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level.value)
    logger.add(LOG_DIR / "cryptopulse.log",
               rotation="10 MB",
               retention="30 days",
               level=settings.log_level.value)


async def main_async(symbol: str, style: str):
    """主异步流程"""
    pipeline = DataPipeline(symbol=symbol, style=style)
    await pipeline.initialize()

    # 设置信号处理
    stop_event = asyncio.Event()

    def _shutdown():
        logger.info("🛑 接收到停止信号，正在关闭...")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _shutdown)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            pass

    # 在另一个任务中运行 WS 连接
    ws_task = asyncio.create_task(pipeline.run())

    # 等待数据就绪后输出首次信号
    await asyncio.sleep(3)
    snapshot = pipeline.get_snapshot()
    klines = snapshot.get("klines", {})
    if any(not df.empty for df in klines.values()):
        for interval, df in klines.items():
            if not df.empty:
                engine = TechnicalSignalEngine(style)
                result = engine.evaluate(df)
                print(format_signal(result, symbol, style))
                break

    # 信号更新循环（每 60 秒）
    async def signal_loop():
        while True:
            await asyncio.sleep(60)
            try:
                snapshot = pipeline.get_snapshot()
                klines = snapshot.get("klines", {})
                if any(not df.empty for df in klines.values()):
                    for interval, df in klines.items():
                        if not df.empty:
                            engine = TechnicalSignalEngine(style)
                            result = engine.evaluate(df)
                            print(format_signal(result, symbol, style))
                            break
            except Exception as e:
                logger.error(f"信号生成失败: {e}")

    signal_task = asyncio.create_task(signal_loop())

    # 等待停止信号
    await stop_event.wait()
    ws_task.cancel()
    signal_task.cancel()
    try:
        await ws_task
    except asyncio.CancelledError:
        pass
    try:
        await signal_task
    except asyncio.CancelledError:
        pass

    await pipeline.stop()
    logger.info(" CryptoPulse 已正常退出")


def main():
    parser = argparse.ArgumentParser(description="CryptoPulse 数据管道")
    parser.add_argument("--symbol", default=settings.default_symbol,
                        help=f"交易对 (默认 {settings.default_symbol})")
    parser.add_argument("--style", default=settings.default_style.value,
                        choices=["short_term", "medium_term"],
                        help="交易风格 (默认 short_term)")
    parser.add_argument("--proxy", default="",
                        help="代理地址，如 http://127.0.0.1:10808")
    args = parser.parse_args()

    if args.proxy:
        os.environ["PROXY"] = args.proxy

    setup_logging()
    setup_proxy()
    logger.info(f" CryptoPulse v0.1.0 启动")
    logger.info(f"   交易对: {args.symbol}")
    logger.info(f"   交易风格: {'短线(1m/5m)' if args.style == 'short_term' else '中线(4h/1d)'}")

    asyncio.run(main_async(args.symbol, args.style))


if __name__ == "__main__":
    main()

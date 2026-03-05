"""
main.py — Entry Point chính của Rabit_FTMO AI Bot (XAGUSD)

Đây là file khởi chạy duy nhất của toàn bộ hệ thống.
Luồng hoạt động dự kiến:
    1. Load cấu hình & credentials từ .env
    2. Khởi tạo DataPipeline (kết nối MT5)
    3. Smoke Test: kéo 5 nến M5 XAGUSD, in DataFrame
    4. Lấy Account Info (nguyên liệu cho Phase 2)
    5. Vòng lặp chính OnTick (Phase 3+)

Phase: 1 — Task 1.3 (Smoke Test + Account Info)

Tác giả: Antigravity (AI Coder)
Ngày cập nhật: 2026-03-05

Cách chạy:
    # Kích hoạt venv trước
    .\\venv\\Scripts\\Activate.ps1

    # Chạy bot
    python main.py
"""

from dotenv import load_dotenv

from utils.logger import system_logger
from core.data_pipeline import MT5DataPipeline
from config.settings import SYMBOL, TIMEFRAME_M5


# ============================================================
# SMOKE TEST CONSTANTS
# ============================================================
SMOKE_CANDLES = 5    # Số nến kéo về để kiểm tra


def main():
    """Entry point chính khởi chạy Rabit_FTMO AI Bot."""

    # --- Bước 1: Load biến môi trường từ .env ---
    load_dotenv()
    system_logger.info("=" * 60)
    system_logger.info("🐇 Rabit_FTMO AI Bot — Khởi động")
    system_logger.info("=" * 60)

    # --- Bước 2: Khởi tạo DataPipeline ---
    pipeline = MT5DataPipeline()

    # --- Bước 3: Kết nối MT5 ---
    system_logger.info("main | Đang kết nối MT5...")
    if not pipeline.connect():
        system_logger.critical(
            "main | ❌ Không thể kết nối MT5. Bot dừng. "
            "Kiểm tra: MT5 Terminal đang mở? .env đúng chưa?"
        )
        return

    # --- Bước 4: Smoke Test — Kéo 5 nến M5 XAGUSD ---
    system_logger.info(
        f"main | 🧪 Smoke Test: Kéo {SMOKE_CANDLES} nến M5 của {SYMBOL}..."
    )

    df = pipeline.fetch_data(
        symbol=SYMBOL,
        timeframe=TIMEFRAME_M5,
        limit=SMOKE_CANDLES
    )

    if df is not None:
        print("\n" + "=" * 70)
        print(f"✅ SMOKE TEST PASSED — {SYMBOL} M5 ({len(df)} nến mới nhất)")
        print("=" * 70)
        # In DataFrame đầy đủ — không truncate cột
        import pandas as pd
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 120)
        print(df.to_string(index=False))
        print("=" * 70)

        # Highlight cột tick_volume để TechLead kiểm tra
        print(f"\n📊 Tick Volume (5 nến):")
        for _, row in df.iterrows():
            print(f"   {row['time']}  →  tick_volume = {row['tick_volume']:>6}")
        print()
    else:
        system_logger.error(
            f"main | ❌ Smoke Test THẤT BẠI — "
            f"fetch_data trả về None cho {SYMBOL} M5. "
            "Kiểm tra symbol có enabled trong Market Watch không."
        )
        pipeline.disconnect()
        return

    # --- Bước 5: Lấy Account Info (nguyên liệu Phase 2) ---
    system_logger.info("main | 💰 Lấy thông tin tài khoản FTMO...")

    account = pipeline.get_account_info()

    if account:
        print("=" * 70)
        print("💰 ACCOUNT INFO (Nguyên liệu Phase 2 — Capital Management)")
        print("=" * 70)
        print(f"   Balance     : {account['balance']:>12,.2f} {account['currency']}")
        print(f"   Equity      : {account['equity']:>12,.2f} {account['currency']}")
        print(f"   Free Margin : {account['margin_free']:>12,.2f} {account['currency']}")
        print(f"   Open P&L    : {account['profit']:>12,.2f} {account['currency']}")
        print(f"   Leverage    : 1:{account['leverage']}")
        print("=" * 70 + "\n")
    else:
        system_logger.warning("main | Không lấy được account info — tiếp tục.")

    # --- Bước 6: Vòng lặp chính (Phase 3+) ---
    # TODO (Task 1.4+): Implement OnTick loop với Strategy Engine
    system_logger.info(
        "main | ✅ Smoke Test & Account Info hoàn tất. "
        "Vòng lặp chính sẽ implement ở Phase 2/3."
    )

    # --- Đóng kết nối sạch ---
    pipeline.disconnect()
    system_logger.info("main | 🔌 Bot tắt an toàn.")


if __name__ == "__main__":
    main()

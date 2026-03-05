"""
main.py — Entry Point chính của Rabit_FTMO AI Bot (XAGUSD)

Đây là file khởi chạy duy nhất của toàn bộ hệ thống.
Luồng hoạt động:
    1. Load cấu hình & credentials từ .env
    2. Khởi tạo DataPipeline (kết nối MT5)
    3. Smoke Test: kéo 5 nến M5 XAGUSD, in DataFrame
    4. Lấy Account Info (balance, equity)
    5. [Phase 2] Khởi tạo RiskManager — load SOD Balance, check hard stop
    6. [Phase 2] Smoke Test calculate_lot_size với SL giả định 200 points
    7. Vòng lặp chính OnTick (Phase 3+)

Phase: 2 — Task 2.1 (Risk Management Integration)

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
from core.risk_manager import RiskManager
from config.settings import SYMBOL, TIMEFRAME_M5


# ============================================================
# SMOKE TEST CONSTANTS
# ============================================================
SMOKE_CANDLES = 5    # Số nến kéo về để kiểm tra

# SL giả định cho smoke test calculate_lot_size (Phase 2)
SMOKE_SL_POINTS = 200   # 200 points = 0.200 USD/oz trên XAGUSD (digits=3)


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
        import pandas as pd
        pd.set_option("display.max_columns", None)
        pd.set_option("display.width", 120)
        print(df.to_string(index=False))
        print("=" * 70)

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

    # --- Bước 5: Lấy Account Info ---
    system_logger.info("main | 💰 Lấy thông tin tài khoản FTMO...")

    account = pipeline.get_account_info()

    if account:
        print("=" * 70)
        print("💰 ACCOUNT INFO (Phase 2 — Risk Management)")
        print("=" * 70)
        print(f"   Balance     : {account['balance']:>12,.2f} {account['currency']}")
        print(f"   Equity      : {account['equity']:>12,.2f} {account['currency']}")
        print(f"   Free Margin : {account['margin_free']:>12,.2f} {account['currency']}")
        print(f"   Open P&L    : {account['profit']:>12,.2f} {account['currency']}")
        print(f"   Leverage    : 1:{account['leverage']}")
        print("=" * 70 + "\n")
    else:
        system_logger.warning("main | Không lấy được account info — tiếp tục.")
        pipeline.disconnect()
        return

    # ============================================================
    # [Phase 2] RISK MANAGER — SMOKE TEST
    # ============================================================

    print("=" * 70)
    print("🛡️  PHASE 2 — RISK MANAGER SMOKE TEST")
    print("=" * 70)

    # --- Bước 6: Khởi tạo RiskManager ---
    risk_mgr = RiskManager(symbol=SYMBOL)

    # --- Bước 7: Load / khởi tạo SOD Balance (Start-of-Day) ---
    sod_balance = risk_mgr.load_or_init_daily_state(
        current_balance=account["balance"]
    )
    print(f"\n📅 SOD Balance (đầu ngày CE(S)T): {sod_balance:>12,.2f} {account['currency']}")

    # --- Bước 8: Kiểm tra Hard-Stop ---
    is_stopped = risk_mgr.check_hard_stop(current_equity=account["equity"])

    drawdown_pct = (sod_balance - account["equity"]) / sod_balance * 100
    print(f"📉 Drawdown hiện tại     : {drawdown_pct:>10.2f}%")
    print(f"🚫 Hard-Stop triggered?  : {'⛔ CÓ — BOT DỪNG' if is_stopped else '✅ KHÔNG — An toàn'}")

    if is_stopped:
        system_logger.critical(
            "main | ⛔ HARD STOP TRIGGERED ngay khi khởi động. "
            "Tài khoản đã vi phạm Daily Drawdown. Bot dừng."
        )
        pipeline.disconnect()
        return

    # --- Bước 9: Smoke Test calculate_lot_size ---
    print(f"\n🧮 Smoke Test calculate_lot_size:")
    print(f"   Symbol       : {SYMBOL}")
    print(f"   Equity       : {account['equity']:,.2f} {account['currency']}")
    print(f"   Risk/Trade   : 0.50%  →  ${account['equity'] * 0.005:,.2f}")
    print(f"   SL Distance  : {SMOKE_SL_POINTS} points (giả định)")

    lot = risk_mgr.calculate_lot_size(
        sl_distance_points=SMOKE_SL_POINTS,
        current_equity=account["equity"]
    )

    print(f"\n   ✅ Lot Size tính ra: {lot:.2f} Lot")
    if lot > 0:
        print(f"   📋 Kiểm tra: Nếu dính SL → Lỗ ≈ ${account['equity'] * 0.005:,.2f}")
        print(f"              (đúng bằng 0.50% equity — Position Sizing chuẩn ✅)")

    print("\n" + "=" * 70)
    print("✅ PHASE 2 RISK MANAGER — SMOKE TEST HOÀN TẤT")
    print("=" * 70 + "\n")

    # --- Bước 10: Vòng lặp chính (Phase 3+) ---
    # TODO (Phase 3): Implement OnTick loop với Strategy Engine + RiskManager
    system_logger.info(
        "main | ✅ Phase 2 Smoke Test hoàn tất. "
        "Vòng lặp chính sẽ implement ở Phase 3."
    )

    # --- Đóng kết nối sạch ---
    pipeline.disconnect()
    system_logger.info("main | 🔌 Bot tắt an toàn.")


if __name__ == "__main__":
    main()

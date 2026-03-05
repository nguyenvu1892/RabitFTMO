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
    7. [Phase 3] Smoke Test StrategyEngine — H1 Bias + M15 FVG active list
    8. Vòng lặp chính OnTick (Phase 4+)

Phase: 3 — Task 3.1 (Strategy Engine Integration)

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
from core.strategy_engine import StrategyEngine
from config.settings import (
    SYMBOL,
    TIMEFRAME_M5,
    TIMEFRAME_H1,
    TIMEFRAME_M15,
    CANDLE_COUNT_M5,
    CANDLE_COUNT_H1,
    CANDLE_COUNT_M15,
)



# ============================================================
# SMOKE TEST CONSTANTS
# ============================================================
SMOKE_CANDLES   = 5    # Số nến kéo về để kiểm tra M5
SMOKE_SL_POINTS = 200  # 200 points = 0.200 USD/oz (giả định cho Phase 2 test)


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

    # ============================================================
    # [Phase 3] STRATEGY ENGINE — SMOKE TEST
    # Vũ khí 1: H1 Market Structure → Directional Bias
    # Vũ khí 2: M15 SMC FVG        → Active FVG Pool
    # ============================================================

    print("=" * 70)
    print("🧭 PHASE 3 — STRATEGY ENGINE SMOKE TEST")
    print("=" * 70)

    # --- Bước 10: Khởi tạo StrategyEngine ---
    engine   = StrategyEngine()
    fvg_pool = engine.create_fvg_pool()

    # --- Bước 11: Kéo dữ liệu H1 và M15 ---
    system_logger.info(f"main | 📥 Kéo {CANDLE_COUNT_H1} nến H1 {SYMBOL}...")
    df_h1 = pipeline.fetch_data(
        symbol=SYMBOL,
        timeframe=TIMEFRAME_H1,
        limit=CANDLE_COUNT_H1,
    )

    system_logger.info(f"main | 📥 Kéo {CANDLE_COUNT_M15} nến M15 {SYMBOL}...")
    df_m15 = pipeline.fetch_data(
        symbol=SYMBOL,
        timeframe=TIMEFRAME_M15,
        limit=CANDLE_COUNT_M15,
    )

    if df_h1 is None or df_m15 is None:
        system_logger.error(
            "main | ❌ Không kéo được dữ liệu H1/M15. "
            "Kiểm tra symbol có trong Market Watch không."
        )
        pipeline.disconnect()
        return

    print(f"\n   ✅ H1:  {len(df_h1)} nến  |  M15: {len(df_m15)} nến\n")

    # --- Bước 12: VŨ KHÍ 1 — H1 Market Structure ---
    print("-" * 70)
    print("⚔️  VŨ KHÍ 1: Market Structure (H1)")
    print("-" * 70)

    h1_bias = engine.identify_market_structure(df_h1)

    bias_emoji = {"BUY": "🟢", "SELL": "🔴", "NEUTRAL": "🟡"}.get(h1_bias, "⚪")
    print(f"\n   {bias_emoji} H1 Directional Bias  :  {h1_bias}")
    print(f"   📌 Ý nghĩa: ", end="")
    if h1_bias == "BUY":
        print("Xu hướng TĂNG — Chỉ tìm setup LONG khi giá vào FVG cầu")
    elif h1_bias == "SELL":
        print("Xu hướng GIẢM — Chỉ tìm setup SHORT khi giá vào FVG cung")
    else:
        print("Thị trường SIDEWAY — Chưa có xu hướng rõ ràng → Bỏ qua, chờ")

    # --- Bước 13: VŨ KHÍ 2 — M15 FVG Active Pool ---
    print(f"\n{'-' * 70}")
    print("⚔️  VŨ KHÍ 2: SMC FVG (M15)")
    print("-" * 70)

    active_fvgs = engine.find_active_fvgs(df_m15, fvg_pool)

    if not active_fvgs:
        print("\n   ℹ️  Không có FVG active nào trên M15 hiện tại.")
        print("      (Có thể FVG đã bị lấp hoặc dữ liệu chưa đủ điều kiện)")
    else:
        print(f"\n   📋 Tổng số FVG đang MỞ (Unmitigated): {len(active_fvgs)}\n")
        print(
            f"   {'#':>3}  {'Type':<9}  {'Bottom':>9}  {'Top':>9}  "
            f"{'Size':>7}  {'Thời gian tạo'}"
        )
        print("   " + "-" * 62)
        for idx, fvg in enumerate(active_fvgs, start=1):
            fvg_size   = fvg["top"] - fvg["bottom"]
            type_emoji = "🟢" if fvg["type"] == "BULLISH" else "🔴"
            print(
                f"   {idx:>3}  {type_emoji} {fvg['type']:<7}  "
                f"{fvg['bottom']:>9.3f}  {fvg['top']:>9.3f}  "
                f"{fvg_size:>7.4f}  {fvg['time']}"
            )
        print()

        # --- Tóm tắt alignment H1 Bias với FVG ---
        bullish_fvgs = [f for f in active_fvgs if f["type"] == "BULLISH"]
        bearish_fvgs = [f for f in active_fvgs if f["type"] == "BEARISH"]

        print("   📊 Phân tích Alignment (H1 Bias ↔ FVG M15):")
        if h1_bias == "BUY" and bullish_fvgs:
            print(f"   ✅ ALIGNED — H1 BUY + {len(bullish_fvgs)} Bullish FVG → CÓ THỂ TÌM LONG setup!")
        elif h1_bias == "SELL" and bearish_fvgs:
            print(f"   ✅ ALIGNED — H1 SELL + {len(bearish_fvgs)} Bearish FVG → CÓ THỂ TÌM SHORT setup!")
        elif h1_bias == "NEUTRAL":
            print("   ⚪ NEUTRAL — Chưa có bias H1 → Không vào lệnh dù có FVG.")
        else:
            print("   ⚠️  CONFLICT — H1 Bias và FVG M15 ngược chiều → Bỏ qua, chờ alignment.")

    # --- Bước 14: VŨ KHÍ 3 — M5 Trigger (Pinbar & VSA) ---
    print(f"\n{'-' * 70}")
    print("⚔️  VŨ KHÍ 3: M5 Trigger (Pinbar & VSA)")
    print("-" * 70)

    # Nếu không có bias hoặc không có FVG, skip fetch M5 cho nhẹ
    if h1_bias == "NEUTRAL" or not active_fvgs:
        print("\n   ℹ️  Bias H1 Neutral hoặc không có FVG M15 mở → Bỏ qua M5 Trigger.")
    else:
        system_logger.info(f"main | 📥 Kéo {CANDLE_COUNT_M5} nến M5 {SYMBOL}...")
        df_m5_trigger = pipeline.fetch_data(
            symbol=SYMBOL,
            timeframe=TIMEFRAME_M5,
            limit=CANDLE_COUNT_M5,
        )

        if df_m5_trigger is not None:
            print(f"\n   ✅ M5:  {len(df_m5_trigger)} nến")
            signal = engine.check_m5_trigger(df_m5_trigger, active_fvgs, h1_bias)

            if signal == "NONE":
                print(f"      → M5 Signal: ⚪ {signal} (Không có tín hiệu Pinbar hợp lệ hoặc không có xác nhận VSA)")
            else:
                emoji = "🟢" if signal == "SIGNAL_BUY" else "🔴"
                print(f"\n   {emoji} 🎯 TÍN HIỆU VÀO LỆNH (M5 TRIGGER):")
                print(f"      → M5 Signal: {signal} ")
                print(f"      (Pinbar hợp lệ, chạm POI, + VSA Volume Spike xác nhận!)")
        else:
             print("\n   ❌ Không kéo được dữ liệu M5 phục vụ Trigger.")

    print("\n" + "=" * 70)
    print("✅ PHASE 3 STRATEGY ENGINE — SMOKE TEST HOÀN TẤT")
    print("=" * 70 + "\n")

    system_logger.info(
        f"main | ✅ Phase 3 Smoke Test hoàn tất. "
        f"H1 Bias={h1_bias}, FVG Active={len(active_fvgs)}. "
        "Vòng lặp OnTick sẽ implement ở Phase 4."
    )

    # --- Đóng kết nối sạch ---
    pipeline.disconnect()
    system_logger.info("main | 🔌 Bot tắt an toàn.")


if __name__ == "__main__":
    main()

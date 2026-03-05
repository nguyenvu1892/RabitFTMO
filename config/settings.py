"""
config/settings.py — Hằng số toàn cục Rabit_FTMO AI

Tất cả các tham số cấu hình được tập trung tại đây.
Không hardcode các giá trị này rải rác trong code — luôn import từ file này.

Thay đổi tham số trading: chỉ cần sửa tại đây, có hiệu lực toàn hệ thống.
"""

import MetaTrader5 as mt5  # noqa: F401 — để lấy hằng số TIMEFRAME_*

# ============================================================
# CẤU HÌNH SYMBOL & MARKET
# ============================================================
SYMBOL = "XAGUSD"          # Cặp giao dịch chính — Bạc/USD

# Khung thời gian theo Multi-Timeframe Logic (CORE_RULES.md Section 3)
TIMEFRAME_H1  = mt5.TIMEFRAME_H1    # H1 — The Compass (Market Structure, Xu hướng)
TIMEFRAME_M15 = mt5.TIMEFRAME_M15   # M15 — POI (FVG Imbalance, Vùng chờ)
TIMEFRAME_M5  = mt5.TIMEFRAME_M5    # M5  — The Trigger (Pinbar, VSA, Entry)

# Số nến tối đa kéo về mỗi lần (đủ để tính Swing High/Low và ATR)
CANDLE_COUNT_H1  = 200
CANDLE_COUNT_M15 = 200
CANDLE_COUNT_M5  = 100

# ============================================================
# CHỈ BÁO KỸ THUẬT (Technical Indicators)
# ============================================================
ATR_PERIOD      = 14        # ATR(14) — Chuẩn CORE_RULES.md (Vũ khí số 5)
VOLUME_MA_PERIOD = 20       # MA20 Volume — Ngưỡng so sánh Tick Volume VSA
PINBAR_RATIO    = 0.6       # Râu nến / Tổng nến >= 60% = Pinbar hợp lệ (có thể tinh chỉnh)

# ============================================================
# QUẢN TRỊ RỦI RO FTMO (Risk Management — CORE_RULES.md Section 2)
# ============================================================
RISK_PER_TRADE      = 0.005   # 0.5% rủi ro mỗi lệnh trên tổng vốn
MAX_DAILY_DRAWDOWN  = 0.045   # 4.5% Hard-Stop — giới hạn FTMO Normal Daily Loss
ATR_SL_MULTIPLIER   = 1.5     # Hệ số ATR tính Stop Loss: SL = Vượt râu + Spread + (1.5 * ATR)
ATR_TP_MULTIPLIER   = 2.0     # Target R:R 1:2 (TP gấp đôi SL theo ATR)
BREAKEVEN_TRIGGER_R = 1.0     # Dời SL về Breakeven khi lãi >= 1R

# ============================================================
# TIMING & TỔ CHỨC PHIÊN (Session Management — CORE_RULES.md Section 2)
# ============================================================
FORCE_CLOSE_HOUR   = 22       # Đóng toàn bộ lệnh trước 22:00 UTC mỗi ngày
FRIDAY_CLOSE_HOUR  = 20       # Đóng hết trước 20:00 UTC thứ Sáu (tránh gap cuối tuần)
NEWS_BLOCK_MINUTES = 30       # Khóa giao dịch trước/sau 30 phút tin Đỏ USD

# ============================================================
# CẤU HÌNH LOG
# ============================================================
LOG_DIR              = "logs"
SYSTEM_LOG_FILE      = "logs/system.log"
TRADE_LOG_FILE       = "logs/trade_decisions.log"

# ============================================================
# VŨ KHÍ 1: MARKET STRUCTURE H1 — AI TUNABLE PARAMETERS
# Phase 5 ML Optimizer sẽ tự động chỉnh các biến này.
# Không hardcode trong strategy_engine.py — luôn import từ đây.
# ============================================================
FRACTAL_PERIOD          = 2    # Số nến mỗi bên để xác nhận Swing High/Low [range: 1–5]
MS_SWING_LOOKBACK       = 50   # Số nến H1 tối đa để tìm Swing trong quá khứ [range: 20–100]
MS_MIN_SWINGS_REQUIRED  = 2    # Số cặp swing tối thiểu để confirm bias (tránh NEUTRAL quá dễ) [range: 1–3]

# ============================================================
# VŨ KHÍ 2: SMC FVG M15 — AI TUNABLE PARAMETERS
# ============================================================
FVG_MIN_GAP_MULTIPLE    = 0.3  # Gap tối thiểu = x × ATR14. Lọc FVG noise quá nhỏ [range: 0.1–1.0]
FVG_IMPULSE_BODY_RATIO  = 0.6  # Tỷ lệ thân/chiều dài nến B (Impulse). 0.6 = thân >= 60% [range: 0.4–0.8]
FVG_MITIGATION_LEVEL    = 0.5  # % FVG cần bị lấp để coi là Mitigated. 0.5 = chuẩn SMC 50% [range: 0.0–1.0]
FVG_MAX_AGE_CANDLES     = 100  # Tuổi thọ tối đa của FVG tính bằng số nến M15 (~25 giờ) [range: 50–200]
FVG_MAX_POOL_SIZE       = 50   # Số FVG active tối đa trong deque — giới hạn RAM [range: 20–100]

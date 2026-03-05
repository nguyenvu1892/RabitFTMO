"""
core/strategy_engine.py — Strategy Engine: Vũ khí 1 & 2 của Rabit_FTMO AI

Triển khai hai vũ khí đầu tiên trong hệ thống 5 Vũ khí cốt lõi (CORE_RULES.md):

  VŨ KHÍ 1 — Market Structure (H1):
      Nhận diện Swing High / Swing Low bằng thuật toán Fractal chuẩn.
      Trả về Directional Bias: 'BUY', 'SELL', hoặc 'NEUTRAL'.
      Anti-Repainting: chỉ dùng nến đã đóng (df.iloc[:-1]).

  VŨ KHÍ 2 — SMC FVG (M15):
      Quét Fair Value Gap (imbalance 3 nến).
      Lưu vào collections.deque(maxlen=FVG_MAX_POOL_SIZE) để kiểm soát RAM.
      Tự động xóa FVG khi giá lấp >= 50% (Mitigated) hoặc FVG quá cũ.

Mọi tham số (FRACTAL_PERIOD, FVG_MIN_GAP_MULTIPLE, ...) được import từ
config/settings.py để Phase 5 ML Optimizer có thể tự động tuning.

Kiến trúc: OOP — Class StrategyEngine, stateless từng lần gọi
(FVG pool được truyền vào ngoài để Caller quản lý vòng đời).

Tác giả: Antigravity (AI Coder)
Phase: 3 — Task 3.1
Ngày: 2026-03-05
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Deque

import pandas as pd

from config.settings import (
    # Vũ khí 1 — Market Structure H1
    FRACTAL_PERIOD,
    MS_SWING_LOOKBACK,
    MS_MIN_SWINGS_REQUIRED,
    # Vũ khí 2 — SMC FVG M15
    ATR_PERIOD,
    FVG_IMPULSE_BODY_RATIO,
    FVG_MAX_AGE_CANDLES,
    FVG_MAX_POOL_SIZE,
    FVG_MIN_GAP_MULTIPLE,
    FVG_MITIGATION_LEVEL,
    # Vũ khí 3 — M5 Trigger (Pinbar + VSA)
    PINBAR_WICK_RATIO,
    PINBAR_BODY_MAX_RATIO,
    ATR_PINBAR_MIN_MULT,
    VSA_VOLUME_MULTIPLIER,
    VOLUME_MA_PERIOD,
)

# Lấy logger từ hệ thống (đã khởi tạo sẵn bởi utils/logger.py)
logger = logging.getLogger("system")

# ---------------------------------------------------------------------------
# Type alias — giúp code đọc rõ hơn và IDE gợi ý kiểu dữ liệu chính xác
# ---------------------------------------------------------------------------
FVGDict = dict  # {"time", "type", "top", "bottom", "mitigated"}
FVGPool = Deque[FVGDict]


# ===========================================================================
# CLASS: StrategyEngine
# ===========================================================================

class StrategyEngine:
    """
    Strategy Engine — Bộ não phân tích kỹ thuật của Rabit_FTMO AI.

    Trách nhiệm:
        - Xác định xu hướng thị trường (Directional Bias) từ khung H1.
        - Tìm và quản lý danh sách các FVG (Point of Interest) từ khung M15.

    Thiết kế stateless cho từng lần gọi:
        - `identify_market_structure` không lưu trạng thái — gọi bao nhiêu lần cũng OK.
        - `find_active_fvgs` nhận vào FVGPool từ Caller để quản lý vòng đời bên ngoài.
          → Caller (main.py) giữ pool, gọi find_active_fvgs mỗi chu kỳ OnTick.

    Ví dụ sử dụng:
        engine   = StrategyEngine()
        fvg_pool = engine.create_fvg_pool()   # Khởi tạo pool một lần duy nhất

        # Mỗi OnTick:
        bias         = engine.identify_market_structure(df_h1)
        active_fvgs  = engine.find_active_fvgs(df_m15, fvg_pool)
    """

    # -----------------------------------------------------------------------
    # KHỞI TẠO
    # -----------------------------------------------------------------------

    def __init__(self) -> None:
        """Khởi tạo StrategyEngine. Log các tham số đang dùng để audit."""
        logger.info(
            "StrategyEngine | Khởi tạo — "
            f"FRACTAL_PERIOD={FRACTAL_PERIOD}, "
            f"MS_SWING_LOOKBACK={MS_SWING_LOOKBACK}, "
            f"FVG_MIN_GAP_MULTIPLE={FVG_MIN_GAP_MULTIPLE}, "
            f"FVG_MITIGATION_LEVEL={FVG_MITIGATION_LEVEL}, "
            f"FVG_MAX_POOL_SIZE={FVG_MAX_POOL_SIZE}"
        )

    # -----------------------------------------------------------------------
    # HELPER: TẠO FVG POOL MỚI
    # -----------------------------------------------------------------------

    @staticmethod
    def create_fvg_pool() -> FVGPool:
        """
        Tạo một deque rỗng để lưu trữ FVG active.

        Caller (main.py) nên gọi hàm này MỘT LẦN khi khởi động bot,
        sau đó truyền pool này vào find_active_fvgs() mỗi chu kỳ OnTick.

        Returns:
            deque với maxlen=FVG_MAX_POOL_SIZE (tự động giới hạn RAM).
        """
        return deque(maxlen=FVG_MAX_POOL_SIZE)

    # -----------------------------------------------------------------------
    # VŨ KHÍ 1: MARKET STRUCTURE H1
    # -----------------------------------------------------------------------

    def identify_market_structure(self, df_h1: pd.DataFrame) -> str:
        """
        Xác định Directional Bias thị trường từ DataFrame H1.

        Thuật toán:
            1. Loại bỏ nến đang chạy (iloc[:-1]) — Anti-Repainting tuyệt đối.
            2. Quét toàn bộ df_safe để tìm Swing High / Swing Low bằng Fractal.
            3. Lấy 2 swing gần nhất cho mỗi loại.
            4. So sánh Higher High + Higher Low → BUY,
                        Lower High + Lower Low  → SELL,
                        Else                    → NEUTRAL.

        Args:
            df_h1 (pd.DataFrame): DataFrame khung H1 từ DataPipeline.
                Cần các cột: ['high', 'low', 'time'].
                Nến cuối cùng (đang chạy) SẼ BỊ BỎ QUA tự động.

        Returns:
            str: 'BUY' | 'SELL' | 'NEUTRAL'
        """
        # --- Guard: DataFrame quá ngắn ---
        min_candles_needed = 2 * FRACTAL_PERIOD + 1
        if df_h1 is None or len(df_h1) < min_candles_needed + 1:
            logger.warning(
                f"StrategyEngine.identify_market_structure | "
                f"DataFrame H1 quá ngắn ({len(df_h1) if df_h1 is not None else 0} nến). "
                f"Cần tối thiểu {min_candles_needed + 1} nến. Trả về NEUTRAL."
            )
            return "NEUTRAL"

        # --- Bước 1: CẮT BỎ NẾN ĐANG CHẠY — Anti-Repainting ---
        # iloc[:-1] → bỏ nến cuối (index -1), chỉ dùng nến đã đóng hoàn toàn.
        # Sau đó giới hạn trong MS_SWING_LOOKBACK nến gần nhất để tăng tốc.
        df_safe = df_h1.iloc[:-1].tail(MS_SWING_LOOKBACK).reset_index(drop=True)

        if len(df_safe) < min_candles_needed:
            logger.warning(
                f"StrategyEngine.identify_market_structure | "
                f"Sau khi cắt nến đang chạy và giới hạn lookback, chỉ còn "
                f"{len(df_safe)} nến. Trả về NEUTRAL."
            )
            return "NEUTRAL"

        # --- Bước 2: Quét Swing High / Swing Low bằng Fractal ---
        swing_highs: list[dict] = []
        swing_lows:  list[dict] = []

        # Phạm vi duyệt: bỏ FRACTAL_PERIOD nến đầu và cuối
        # vì chúng không đủ nến hai bên để so sánh Fractal.
        scan_start = FRACTAL_PERIOD
        scan_end   = len(df_safe) - FRACTAL_PERIOD  # exclusive

        for i in range(scan_start, scan_end):
            if self._is_swing_high(df_safe, i, FRACTAL_PERIOD):
                swing_highs.append({
                    "index": i,
                    "time":  df_safe["time"].iloc[i],
                    "high":  df_safe["high"].iloc[i],
                })

            if self._is_swing_low(df_safe, i, FRACTAL_PERIOD):
                swing_lows.append({
                    "index": i,
                    "time":  df_safe["time"].iloc[i],
                    "low":   df_safe["low"].iloc[i],
                })

        logger.debug(
            f"StrategyEngine.identify_market_structure | "
            f"Tìm thấy {len(swing_highs)} Swing High, {len(swing_lows)} Swing Low "
            f"trong {len(df_safe)} nến H1 đã đóng."
        )

        # --- Bước 3: Kiểm tra đủ dữ liệu để xác định bias ---
        if (len(swing_highs) < MS_MIN_SWINGS_REQUIRED
                or len(swing_lows) < MS_MIN_SWINGS_REQUIRED):
            logger.info(
                f"StrategyEngine.identify_market_structure | "
                f"Không đủ swing để xác định bias "
                f"(SH={len(swing_highs)}, SL={len(swing_lows)}, "
                f"cần tối thiểu {MS_MIN_SWINGS_REQUIRED}). Trả về NEUTRAL."
            )
            return "NEUTRAL"

        # --- Bước 4: Lấy 2 Swing gần nhất và so sánh ---
        # Danh sách swing_highs/lows đã được sắp theo index tăng dần (quét từ trái → phải).
        # → [-2] là swing gần thứ 2, [-1] là swing gần nhất.
        sh_prev = swing_highs[-2]
        sh_last = swing_highs[-1]
        sl_prev = swing_lows[-2]
        sl_last = swing_lows[-1]

        is_higher_high = sh_last["high"] > sh_prev["high"]   # Higher High
        is_higher_low  = sl_last["low"]  > sl_prev["low"]    # Higher Low
        is_lower_high  = sh_last["high"] < sh_prev["high"]   # Lower High
        is_lower_low   = sl_last["low"]  < sl_prev["low"]    # Lower Low

        if is_higher_high and is_higher_low:
            bias = "BUY"
        elif is_lower_high and is_lower_low:
            bias = "SELL"
        else:
            bias = "NEUTRAL"

        logger.info(
            f"StrategyEngine.identify_market_structure | "
            f"H1 Bias = {bias} | "
            f"SH: {sh_prev['high']:.3f} → {sh_last['high']:.3f} ({'HH' if is_higher_high else 'LH'}) | "
            f"SL: {sl_prev['low']:.3f} → {sl_last['low']:.3f} ({'HL' if is_higher_low else 'LL'})"
        )
        return bias

    # -----------------------------------------------------------------------
    # VŨ KHÍ 2: SMC FVG M15
    # -----------------------------------------------------------------------

    def find_active_fvgs(
        self,
        df_m15: pd.DataFrame,
        fvg_pool: FVGPool,
    ) -> list[FVGDict]:
        """
        Quét FVG mới từ DataFrame M15, cập nhật pool, và trả về danh sách FVG active.

        Luồng xử lý mỗi lần gọi:
            1. Cắt nến đang chạy → df_safe (Anti-Repainting).
            2. Tính ATR14 trên df_safe để lọc FVG noise.
            3. Quét toàn bộ df_safe, phát hiện FVG mới (3-candle pattern).
               Chỉ thêm FVG chưa có trong pool (dùng timestamp nến B làm key).
            4. Kiểm tra từng FVG trong pool:
               - Đánh dấu Mitigated nếu giá hiện tại lấp >= 50% FVG.
               - Đánh dấu Expired nếu FVG quá cũ (> FVG_MAX_AGE_CANDLES nến).
            5. Lọc pool: chỉ giữ FVG chưa Mitigated và chưa Expired.
            6. Trả về list FVG còn active dưới dạng list (để Caller in/xử lý).

        Args:
            df_m15 (pd.DataFrame): DataFrame khung M15.
                Cần các cột: ['time', 'open', 'high', 'low', 'close'].
            fvg_pool (FVGPool): deque do Caller quản lý.
                Truyền vào cùng pool mỗi chu kỳ để tích lũy FVG qua các lần gọi.

        Returns:
            list[FVGDict]: Danh sách FVG đang active, mỗi phần tử gồm:
                {
                    "time"      : pd.Timestamp,  # Lúc nến B đóng
                    "type"      : "BULLISH" | "BEARISH",
                    "top"       : float,           # Cạnh trên FVG
                    "bottom"    : float,           # Cạnh dưới FVG
                    "mitigated" : bool,            # True nếu đã bị lấp
                }
        """
        # --- Guard: DataFrame quá ngắn (cần ít nhất 3 nến đã đóng + 1 đang chạy) ---
        if df_m15 is None or len(df_m15) < 4:
            logger.warning(
                f"StrategyEngine.find_active_fvgs | "
                f"DataFrame M15 quá ngắn ({len(df_m15) if df_m15 is not None else 0} nến). "
                "Cần ít nhất 4 nến. Trả về pool hiện tại."
            )
            return list(fvg_pool)

        # --- Bước 1: Cắt nến đang chạy — Anti-Repainting ---
        df_safe = df_m15.iloc[:-1].reset_index(drop=True)

        # Giá hiện tại = close của nến M15 đang chạy (OK để check mitigation —
        # đây là price action kiểm tra, không phải điểm nhận diện cấu trúc).
        current_price = float(df_m15["close"].iloc[-1])

        # --- Bước 2: Tính ATR14 trên nến đã đóng ---
        atr_value = self._calculate_atr(df_safe, ATR_PERIOD)

        # --- Bước 3: Quét FVG mới từ df_safe ---
        # Tập hợp timestamp đã có trong pool để tránh trùng lặp O(1)
        existing_fvg_times: set = {fvg["time"] for fvg in fvg_pool}

        # Duyệt bộ 3 nến: A = i-1, B = i, C = i+1
        # Giới hạn: i phải có i+1 hợp lệ → scan đến len-2 (exclusive len-1)
        for i in range(1, len(df_safe) - 1):
            candle_a = df_safe.iloc[i - 1]
            candle_b = df_safe.iloc[i]
            candle_c = df_safe.iloc[i + 1]

            fvg_time_key = candle_b["time"]  # Dùng timestamp nến B làm unique key

            # Bỏ qua FVG đã có trong pool
            if fvg_time_key in existing_fvg_times:
                continue

            # --- Phát hiện Bullish FVG ---
            if candle_c["low"] > candle_a["high"]:
                gap_size = float(candle_c["low"]) - float(candle_a["high"])
                if self._is_valid_fvg(gap_size, candle_b, atr_value):
                    new_fvg: FVGDict = {
                        "time":       fvg_time_key,
                        "type":       "BULLISH",
                        "top":        float(candle_c["low"]),
                        "bottom":     float(candle_a["high"]),
                        "mitigated":  False,
                    }
                    fvg_pool.append(new_fvg)
                    existing_fvg_times.add(fvg_time_key)
                    logger.debug(
                        f"StrategyEngine.find_active_fvgs | "
                        f"[+] Bullish FVG @ {fvg_time_key} | "
                        f"bottom={new_fvg['bottom']:.3f}, top={new_fvg['top']:.3f}, "
                        f"gap={gap_size:.4f}, atr={atr_value:.4f}"
                    )

            # --- Phát hiện Bearish FVG ---
            elif candle_c["high"] < candle_a["low"]:
                gap_size = float(candle_a["low"]) - float(candle_c["high"])
                if self._is_valid_fvg(gap_size, candle_b, atr_value):
                    new_fvg = {
                        "time":       fvg_time_key,
                        "type":       "BEARISH",
                        "top":        float(candle_a["low"]),
                        "bottom":     float(candle_c["high"]),
                        "mitigated":  False,
                    }
                    fvg_pool.append(new_fvg)
                    existing_fvg_times.add(fvg_time_key)
                    logger.debug(
                        f"StrategyEngine.find_active_fvgs | "
                        f"[+] Bearish FVG @ {fvg_time_key} | "
                        f"bottom={new_fvg['bottom']:.3f}, top={new_fvg['top']:.3f}, "
                        f"gap={gap_size:.4f}, atr={atr_value:.4f}"
                    )

        # --- Bước 4: Kiểm tra Mitigation và Age cho toàn bộ pool ---
        current_candle_idx = len(df_safe) - 1

        # Tạo map: timestamp → index (để tính tuổi FVG)
        time_to_idx: dict = {
            row["time"]: idx
            for idx, row in df_safe.iterrows()
        }

        for fvg in fvg_pool:
            # Skip FVG đã bị đánh dấu Mitigated trước đó
            if fvg.get("mitigated"):
                continue

            # Kiểm tra Age (FVG quá cũ → expired)
            fvg_origin_idx = time_to_idx.get(fvg["time"])
            if fvg_origin_idx is not None:
                age_candles = current_candle_idx - fvg_origin_idx
                if age_candles > FVG_MAX_AGE_CANDLES:
                    fvg["mitigated"] = True   # Dùng lại flag "mitigated" để thống nhất
                    logger.debug(
                        f"StrategyEngine.find_active_fvgs | "
                        f"[~] FVG {fvg['type']} @ {fvg['time']} EXPIRED "
                        f"(age={age_candles} > {FVG_MAX_AGE_CANDLES} nến)"
                    )
                    continue

            # Kiểm tra Mitigation (giá lấp FVG >= 50%)
            fvg_size   = fvg["top"] - fvg["bottom"]
            if fvg_size <= 0:
                fvg["mitigated"] = True
                continue

            mitigation_price = fvg["bottom"] + fvg_size * FVG_MITIGATION_LEVEL

            if fvg["type"] == "BULLISH":
                # Bullish FVG bị lấp khi giá giảm xuống <= midpoint
                if current_price <= mitigation_price:
                    fvg["mitigated"] = True
                    logger.info(
                        f"StrategyEngine.find_active_fvgs | "
                        f"[x] Bullish FVG @ {fvg['time']} MITIGATED "
                        f"(price={current_price:.3f} <= {mitigation_price:.3f})"
                    )

            elif fvg["type"] == "BEARISH":
                # Bearish FVG bị lấp khi giá tăng lên >= midpoint
                if current_price >= mitigation_price:
                    fvg["mitigated"] = True
                    logger.info(
                        f"StrategyEngine.find_active_fvgs | "
                        f"[x] Bearish FVG @ {fvg['time']} MITIGATED "
                        f"(price={current_price:.3f} >= {mitigation_price:.3f})"
                    )

        # --- Bước 5: Lọc pool — chỉ giữ FVG chưa bị Mitigated/Expired ---
        # Tạo deque mới từ filter (giữ nguyên maxlen)
        active = [fvg for fvg in fvg_pool if not fvg.get("mitigated")]

        # Cập nhật lại pool: thay nội dung bằng các FVG còn active
        fvg_pool.clear()
        fvg_pool.extend(active)

        logger.info(
            f"StrategyEngine.find_active_fvgs | "
            f"FVG active: {len(active)} "
            f"[Bullish: {sum(1 for f in active if f['type']=='BULLISH')}, "
            f"Bearish: {sum(1 for f in active if f['type']=='BEARISH')}]"
        )

        return active

    # -----------------------------------------------------------------------
    # VŨ KHÍ 3: M5 TRIGGER (PINBAR + VSA)
    # -----------------------------------------------------------------------

    def check_m5_trigger(
        self,
        df_m5: pd.DataFrame,
        active_fvgs: list[FVGDict],
        h1_bias: str
    ) -> str:
        """
        Kiểm tra nến M5 hiện tại có phải là tín hiệu vào lệnh (Trigger) hợp lệ không.

        Luồng xử lý (6 bước lọc):
            1. Guard: Check H1 Bias và Active FVGs.
            2. Lấy nến M5 đã đóng gần nhất (Anti-Repainting).
            3. Tính ATR14, loại bỏ Pinbar quá nhỏ do spread giãn.
            4. Phân tích 3-Ratio System (Wick, Body) để xác định Hammer / Shooting Star.
            5. Kiểm tra Alignment (Bias ↔ Pinbar type) và POI (nến M5 nằm trong FVG hợp lệ).
            6. Phân tích VSA (Volume Spike >= 1.5x SMA20) để xác nhận Smart Money.

        Args:
            df_m5 (pd.DataFrame): DataFrame khung M5.
            active_fvgs (list[FVGDict]): Danh sách FVG M15 đang active (được trả về từ VŨ KHÍ 2).
            h1_bias (str): 'BUY', 'SELL', 'NEUTRAL' (được trả về từ VŨ KHÍ 1).

        Returns:
            str: 'SIGNAL_BUY' | 'SIGNAL_SELL' | 'NONE'
        """
        # --- Guard 1: Yêu cầu dữ liệu M5 đủ tính VSA (SMA20) và nến đóng ---
        min_m5_candles = VOLUME_MA_PERIOD + 1
        if df_m5 is None or len(df_m5) < min_m5_candles:
            logger.warning(
                f"StrategyEngine.check_m5_trigger | "
                f"Data M5 không đủ ({len(df_m5) if df_m5 is not None else 0}). "
                f"Cần >= {min_m5_candles} nến. Trả về NONE."
            )
            return "NONE"

        # --- Guard 2: H1 Bias = NEUTRAL, hoặc không có FVG M15 mở ---
        if h1_bias == "NEUTRAL":
            logger.debug("StrategyEngine.check_m5_trigger | H1 Bias = NEUTRAL, bỏ qua trigger.")
            return "NONE"

        if not active_fvgs:
            logger.debug("StrategyEngine.check_m5_trigger | Không có FVG M15 active, bỏ qua trigger.")
            return "NONE"

        # --- Bước 1: Anti-Repainting — Lấy nến M5 cuối cùng ĐÃ ĐÓNG ---
        # index -1 là nến đang mở. index -2 là nến ĐÃ ĐÓNG gần nhất.
        trigger_candle = df_m5.iloc[-2]
        time_m5 = trigger_candle["time"]

        # Để tính SMA volume an toàn (anti-repainting), ta lấy -VOLUME_MA_PERIOD nến ĐÃ ĐÓNG
        df_m5_safe = df_m5.iloc[:-1].reset_index(drop=True)
        # --- Tính ATR14 cho nến đóng ---
        atr_value = self._calculate_atr(df_m5_safe, ATR_PERIOD)

        if atr_value is None or atr_value == 0:
            logger.warning(
                f"StrategyEngine.check_m5_trigger | [{time_m5}] "
                f"Chưa đủ data tính ATR M5. Trả về NONE."
            )
            return "NONE"

        # Tách thuộc tính nến
        open_p  = float(trigger_candle["open"])
        high_p  = float(trigger_candle["high"])
        low_p   = float(trigger_candle["low"])
        close_p = float(trigger_candle["close"])
        vol     = float(trigger_candle["tick_volume"])

        c_range = high_p - low_p

        # --- Bước 2: Kiểm tra Size (lọc Spread noise) ---
        if c_range < ATR_PINBAR_MIN_MULT * atr_value:
            logger.debug(
                f"StrategyEngine.check_m5_trigger | [{time_m5}] Loại Pinbar rởm. "
                f"Range={c_range:.3f} < {ATR_PINBAR_MIN_MULT:.2f} × ATR({atr_value:.3f})."
            )
            return "NONE"

        # --- Bước 3: Toán học 3-Ratio (Pinbar Pattern) ---
        uw = high_p - max(open_p, close_p)
        lw = min(open_p, close_p) - low_p
        body = abs(close_p - open_p)

        is_hammer = (
            (lw / c_range >= PINBAR_WICK_RATIO) and
            (uw / c_range <= PINBAR_BODY_MAX_RATIO) and
            (body / c_range <= PINBAR_BODY_MAX_RATIO)
        )

        is_shooting_star = (
            (uw / c_range >= PINBAR_WICK_RATIO) and
            (lw / c_range <= PINBAR_BODY_MAX_RATIO) and
            (body / c_range <= PINBAR_BODY_MAX_RATIO)
        )

        if is_hammer:
            candle_type = "HAMMER"
        elif is_shooting_star:
            candle_type = "SHOOTING_STAR"
        else:
            return "NONE" # Không phải Pinbar

        # --- Bước 4: Kiểm tra Alignment (Bias H1 vs Pinbar type) ---
        if h1_bias == "BUY" and candle_type != "HAMMER":
            logger.debug(f"StrategyEngine.check_m5_trigger | [{time_m5}] Counter-trend ({h1_bias} vs {candle_type}).")
            return "NONE"
        if h1_bias == "SELL" and candle_type != "SHOOTING_STAR":
            logger.debug(f"StrategyEngine.check_m5_trigger | [{time_m5}] Counter-trend ({h1_bias} vs {candle_type}).")
            return "NONE"

        # --- Bước 5: Kiểm tra POI (Giao thoa M5 ↔ FVG M15) ---
        matching_fvg = self._find_matching_fvg(high_p, low_p, candle_type, active_fvgs)
        if matching_fvg is None:
            logger.debug(
                f"StrategyEngine.check_m5_trigger | [{time_m5}] "
                f"{candle_type} Pinbar hợp lệ NHƯNG xảy ra ngoài vùng FVG M15 (random zone)."
            )
            return "NONE"

        # --- Bước 6: Phân tích VSA (Volume Spike) ---
        # Tính SMA20 Volume (chỉ lấy nến đã đóng, tối đa 20 nến tính từ nến trigger)
        vol_series_safe = df_m5_safe["tick_volume"].tail(VOLUME_MA_PERIOD)
        vol_ma = vol_series_safe.mean()

        if vol_ma == 0:
            return "NONE" # Tránh div/0

        vol_ratio = vol / vol_ma

        if vol_ratio < VSA_VOLUME_MULTIPLIER:
            logger.info(
                f"StrategyEngine.check_m5_trigger | [{time_m5}] {candle_type} TẠI FVG {matching_fvg['time']} BỊ TỪ CHỐI "
                f"do VSA Volume thấp: {vol_ratio:.2f}x SMA20 (yêu cầu >= {VSA_VOLUME_MULTIPLIER:.2f}x)."
            )
            return "NONE"

        # === ĐÃ PASS TẤT CẢ ==
        signal = "SIGNAL_BUY" if candle_type == "HAMMER" else "SIGNAL_SELL"

        logger.info(
            f"StrategyEngine.check_m5_trigger | [{time_m5}] 🎯 {signal} TRIGGERED! "
            f"H1={h1_bias} | M15_FVG={matching_fvg['type']}@{matching_fvg['time']} | "
            f"M5_{candle_type} (VSA confirmed: Vol={vol_ratio:.2f}x SMA20)."
        )

        return signal

    # -----------------------------------------------------------------------
    # PRIVATE HELPERS
    # -----------------------------------------------------------------------

    def _is_candle_in_fvg(self, candle_high: float, candle_low: float, fvg: FVGDict) -> bool:
        """Kiểm tra nến (M5) có giao cắt (overlap) với FVG không."""
        return (candle_low <= fvg["top"]) and (candle_high >= fvg["bottom"])

    def _find_matching_fvg(self, candle_high: float, candle_low: float, candle_type: str, active_fvgs: list[FVGDict]) -> FVGDict | None:
        """
        Tìm FVG phù hợp với Pinbar.
        Mua (HAMMER) cần chạm Bullsih FVG. Bán (SHOOTING_STAR) cần chạm Bearish FVG.
        """
        required_fvg_type = "BULLISH" if candle_type == "HAMMER" else "BEARISH"

        matching_fvgs = [
            fvg for fvg in active_fvgs
            if fvg["type"] == required_fvg_type
            and self._is_candle_in_fvg(candle_high, candle_low, fvg)
        ]

        if matching_fvgs:
            return matching_fvgs[-1] # Ưu tiên FVG mới nhất (gần đây nhất)
        return None

    def _is_swing_high(self, df: pd.DataFrame, i: int, period: int) -> bool:
        """
        Kiểm tra nến tại index i có phải Swing High (Fractal) không.

        Điều kiện: high[i] > high[i-j] và high[i] > high[i+j] với mọi j trong [1, period].
        Dùng strict > (không dùng >=) để tránh gán swing cho các nến high bằng nhau.

        Args:
            df (pd.DataFrame): DataFrame đã reset_index (index 0..n-1).
            i (int): Index nến cần kiểm tra.
            period (int): FRACTAL_PERIOD — số nến mỗi bên.

        Returns:
            bool: True nếu là Swing High hợp lệ.
        """
        center_high = df["high"].iloc[i]
        for j in range(1, period + 1):
            if center_high <= df["high"].iloc[i - j]:
                return False
            if center_high <= df["high"].iloc[i + j]:
                return False
        return True

    def _is_swing_low(self, df: pd.DataFrame, i: int, period: int) -> bool:
        """
        Kiểm tra nến tại index i có phải Swing Low (Fractal) không.

        Điều kiện: low[i] < low[i-j] và low[i] < low[i+j] với mọi j trong [1, period].

        Args:
            df (pd.DataFrame): DataFrame đã reset_index.
            i (int): Index nến cần kiểm tra.
            period (int): FRACTAL_PERIOD.

        Returns:
            bool: True nếu là Swing Low hợp lệ.
        """
        center_low = df["low"].iloc[i]
        for j in range(1, period + 1):
            if center_low >= df["low"].iloc[i - j]:
                return False
            if center_low >= df["low"].iloc[i + j]:
                return False
        return True

    def _is_valid_fvg(
        self,
        gap_size: float,
        candle_b: pd.Series,
        atr_value: float | None,
    ) -> bool:
        """
        Kiểm tra FVG có đủ chất lượng để thêm vào pool không.

        Hai bộ lọc:
            1. Gap tối thiểu: gap_size >= FVG_MIN_GAP_MULTIPLE × ATR.
               Nếu ATR không tính được (None hoặc 0), bộ lọc này được bỏ qua.
            2. Nến B là Impulse: body_B / range_B >= FVG_IMPULSE_BODY_RATIO.
               Nến B phải có thân nến mạnh (>= 60%) → xác nhận lực đẩy thực sự.

        Args:
            gap_size (float): Kích thước khoảng trống FVG (đã tính dương).
            candle_b (pd.Series): Dữ liệu nến B (nến giữa).
            atr_value (float | None): Giá trị ATR14 hiện tại.

        Returns:
            bool: True nếu FVG hợp lệ.
        """
        # Bộ lọc 1: Gap tối thiểu theo ATR
        if atr_value is not None and atr_value > 0:
            if gap_size < FVG_MIN_GAP_MULTIPLE * atr_value:
                return False

        # Bộ lọc 2: Nến B phải là Impulse (thân/chiều dài nến)
        range_b = float(candle_b["high"]) - float(candle_b["low"])
        if range_b <= 0:
            return False  # Nến doji hoàn toàn — không hợp lệ
        body_b = abs(float(candle_b["close"]) - float(candle_b["open"]))
        if body_b / range_b < FVG_IMPULSE_BODY_RATIO:
            return False

        return True

    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period: int) -> float | None:
        """
        Tính True Range trung bình (ATR) theo Wilder's RMA.

        Công thức:
            True Range (TR) = max(high, prev_close) - min(low, prev_close)
            ATR = RMA(TR, period)  [Wilder's Smoothed Moving Average]

        Args:
            df (pd.DataFrame): DataFrame đã có cột 'high', 'low', 'close'.
            period (int): Chu kỳ ATR (mặc định ATR_PERIOD = 14).

        Returns:
            float | None: Giá trị ATR nến mới nhất, hoặc None nếu dữ liệu không đủ.
        """
        if len(df) < period + 1:
            logger.warning(
                f"StrategyEngine._calculate_atr | "
                f"DataFrame chỉ có {len(df)} nến, cần ít nhất {period + 1} để tính ATR{period}. "
                "ATR trả về None — bộ lọc gap FVG sẽ bị bỏ qua."
            )
            return None

        high  = df["high"].astype(float)
        low   = df["low"].astype(float)
        close = df["close"].astype(float)

        # True Range
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)

        # Wilder's RMA: khởi tạo bằng SMA period đầu tiên, sau đó exponential
        atr_series = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
        return float(atr_series.iloc[-1])

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
    # PRIVATE HELPERS
    # -----------------------------------------------------------------------

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

"""
core/data_pipeline.py — Module kéo dữ liệu thị trường từ MetaTrader 5

Chức năng:
    - Kết nối an toàn vào tài khoản MT5 bằng credentials từ .env
    - Kéo dữ liệu nến OHLCV (Open, High, Low, Close, Tick Volume) của XAGUSD
      trên các khung thời gian M5, M15, H1.
    - In-Memory Cache với TTL: tránh spam request trong chu kỳ ngắn.
    - Auto-Reconnect: tự động thử lại tối đa 3 lần khi mất kết nối.
    - Xử lý lỗi có tầng (Try/Except) và log chi tiết ra system.log.
    - Trả về DataFrame chuẩn UTC cho strategy_engine.py xử lý tiếp.

Kiến trúc:
    class MT5DataPipeline
        connect()             -> bool
        fetch_data(...)       -> pd.DataFrame | None
        disconnect()          -> None
        _get_from_cache(...)  -> pd.DataFrame | None   [private]
        _set_cache(...)       -> None                  [private]

Phase: 1 — Task 1.2

Phụ thuộc:
    - MetaTrader5  >= 5.0.45
    - pandas       >= 2.0.0
    - python-dotenv >= 1.0.0

Tác giả    : Antigravity (AI Coder)
TechLead   : Đã duyệt — 2026-03-05
"""

import os
import time
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv

from utils.logger import system_logger
from config.settings import (
    SYMBOL,
    TIMEFRAME_M5,
    TIMEFRAME_M15,
    TIMEFRAME_H1,
    CANDLE_COUNT_M5,
    CANDLE_COUNT_M15,
    CANDLE_COUNT_H1,
)

# ============================================================
# CONSTANTS
# ============================================================

# Số lần retry tối đa khi connect hoặc fetch thất bại
MAX_RETRY_ATTEMPTS = 3

# Khoảng thời gian chờ giữa mỗi lần retry (giây)
RETRY_DELAY_SECONDS = 2.0

# TTL (Time-To-Live) cache theo từng timeframe (giây)
# Lý do: Nến M5 đóng sau 5 phút — cache 30s là an toàn, không bỏ lỡ nến mới
CACHE_TTL = {
    TIMEFRAME_M5:  30,    # 30 giây cho M5
    TIMEFRAME_M15: 60,    # 60 giây cho M15
    TIMEFRAME_H1:  120,   # 2 phút cho H1 (nến 60 phút — không cần kéo thường)
}

# Các cột chuẩn trả về cho downstream modules
REQUIRED_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume"]


# ============================================================
# CLASS MT5DataPipeline
# ============================================================

class MT5DataPipeline:
    """
    Pipeline kéo dữ liệu OHLCV từ MetaTrader 5.

    Sử dụng:
        pipeline = MT5DataPipeline()
        if pipeline.connect():
            df = pipeline.fetch_data(SYMBOL, TIMEFRAME_M5, CANDLE_COUNT_M5)
            # ... xử lý df ...
            pipeline.disconnect()

    Attributes:
        _is_connected (bool)   : Trạng thái kết nối hiện tại.
        _cache (dict)          : In-memory cache {cache_key: pd.DataFrame}.
        _cache_timestamps (dict): Timestamp lúc cache được ghi {cache_key: float}.
    """

    def __init__(self):
        """
        Khởi tạo pipeline:
        - Load .env để chuẩn bị credentials (KHÔNG kết nối MT5 ngay).
        - Khởi tạo cache và trạng thái kết nối.
        """
        load_dotenv()
        self._is_connected: bool = False
        self._cache: dict[str, pd.DataFrame] = {}
        self._cache_timestamps: dict[str, float] = {}

        system_logger.info("MT5DataPipeline | Khởi tạo pipeline — .env đã load, cache sẵn sàng.")

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------

    def connect(self) -> bool:
        """
        Kết nối tới MetaTrader 5 Terminal với credentials từ .env.

        Luồng xử lý:
            1. Đọc và validate MT5_LOGIN, MT5_PASSWORD, MT5_SERVER từ env.
            2. Gọi mt5.initialize() — khởi động kênh IPC với terminal.
            3. Gọi mt5.login() — xác thực tài khoản FTMO.
            4. Xác nhận kết nối bằng mt5.account_info().
            5. Retry tối đa MAX_RETRY_ATTEMPTS lần nếu thất bại.

        Returns:
            bool: True nếu kết nối thành công, False nếu thất bại hoàn toàn.
        """
        # --- Tầng 1: Validate environment variables (fail-fast) ---
        login_str = os.getenv("MT5_LOGIN", "")
        password = os.getenv("MT5_PASSWORD", "")
        server = os.getenv("MT5_SERVER", "")

        if not login_str or not password or not server:
            system_logger.error(
                "MT5DataPipeline.connect | THIẾU CREDENTIALS: "
                "Kiểm tra MT5_LOGIN, MT5_PASSWORD, MT5_SERVER trong file .env"
            )
            return False

        try:
            login = int(login_str)
        except ValueError:
            system_logger.error(
                f"MT5DataPipeline.connect | MT5_LOGIN không hợp lệ: '{login_str}' "
                "phải là số nguyên (số tài khoản MT5)."
            )
            return False

        # --- Retry loop ---
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            system_logger.info(
                f"MT5DataPipeline.connect | Lần thử {attempt}/{MAX_RETRY_ATTEMPTS} — "
                f"Login: {login} | Server: {server}"
            )

            # --- Tầng 2: mt5.initialize() ---
            if not mt5.initialize():
                err = mt5.last_error()
                system_logger.error(
                    f"MT5DataPipeline.connect | mt5.initialize() THẤT BẠI "
                    f"[attempt {attempt}] — Lỗi: {err}. "
                    "Hãy chắc chắn MT5 Terminal đang mở và đăng nhập."
                )
                self._wait_before_retry(attempt)
                continue

            # --- Tầng 3: mt5.login() ---
            authorized = mt5.login(
                login=login,
                password=password,
                server=server
            )

            if not authorized:
                err = mt5.last_error()
                # Log LOGIN và SERVER nhưng KHÔNG log PASSWORD
                system_logger.error(
                    f"MT5DataPipeline.connect | mt5.login() THẤT BẠI "
                    f"[attempt {attempt}] — Login: {login} | Server: {server} | "
                    f"Lỗi MT5: {err}"
                )
                mt5.shutdown()
                self._wait_before_retry(attempt)
                continue

            # --- Tầng 4: Xác nhận account info ---
            info = mt5.account_info()
            if info is None:
                system_logger.error(
                    f"MT5DataPipeline.connect | account_info() trả về None "
                    f"[attempt {attempt}] — Kết nối không ổn định."
                )
                mt5.shutdown()
                self._wait_before_retry(attempt)
                continue

            # --- Thành công ---
            self._is_connected = True
            system_logger.info(
                f"MT5DataPipeline.connect | ✅ KẾT NỐI THÀNH CÔNG — "
                f"Login: {info.login} | Server: {info.server} | "
                f"Balance: {info.balance:.2f} {info.currency} | "
                f"Leverage: 1:{info.leverage}"
            )
            return True

        # --- Hết retry, vẫn thất bại ---
        system_logger.error(
            f"MT5DataPipeline.connect | ❌ THẤT BẠI HOÀN TOÀN sau {MAX_RETRY_ATTEMPTS} lần thử. "
            "Bot sẽ không chạy. Kiểm tra Terminal, tài khoản, hoặc kết nối mạng."
        )
        return False

    def fetch_data(
        self,
        symbol: str,
        timeframe: int,
        limit: int
    ) -> pd.DataFrame | None:
        """
        Kéo dữ liệu OHLCV từ MT5 và trả về DataFrame chuẩn.

        Args:
            symbol    (str): Tên cặp giao dịch, vd: "XAGUSD".
            timeframe (int): Hằng số mt5.TIMEFRAME_*, vd: mt5.TIMEFRAME_M5.
            limit     (int): Số nến muốn kéo (kéo từ nến mới nhất trở về).

        Returns:
            pd.DataFrame: Các cột [time, open, high, low, close, tick_volume].
                          Cột `time` là datetime64[ns, UTC] — timezone-aware.
            None        : Nếu có lỗi ở bất kỳ tầng nào.

        Cache:
            Kết quả được cache trong bộ nhớ theo TTL của từng timeframe.
            Gọi lại trong cửa sổ TTL sẽ trả về data từ cache (không tốn request).
        """
        if not self._is_connected:
            system_logger.warning(
                "MT5DataPipeline.fetch_data | Chưa kết nối MT5. "
                "Gọi connect() trước khi fetch_data()."
            )
            return None

        # --- Kiểm tra cache trước ---
        cached = self._get_from_cache(symbol, timeframe, limit)
        if cached is not None:
            return cached

        # --- Retry loop ---
        for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
            # --- Tầng 4: copy_rates_from_pos ---
            # start_pos=0: bắt đầu từ nến mới nhất (most recent bar)
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, limit)

            if rates is None or len(rates) == 0:
                err = mt5.last_error()
                system_logger.warning(
                    f"MT5DataPipeline.fetch_data | copy_rates_from_pos trả về None/rỗng "
                    f"[attempt {attempt}/{MAX_RETRY_ATTEMPTS}] — "
                    f"Symbol: {symbol} | TF: {timeframe} | Lỗi: {err}. "
                    "Kiểm tra symbol có enabled trong Market Watch không."
                )

                # Thử reconnect rồi retry
                if attempt < MAX_RETRY_ATTEMPTS:
                    system_logger.info(
                        f"MT5DataPipeline.fetch_data | Thử reconnect trước lần {attempt + 1}..."
                    )
                    mt5.shutdown()
                    self._is_connected = False
                    if not self.connect():
                        system_logger.error(
                            "MT5DataPipeline.fetch_data | Reconnect thất bại — dừng retry."
                        )
                        return None
                    self._wait_before_retry(attempt)
                continue

            # --- Tầng 5: Convert sang DataFrame ---
            df = pd.DataFrame(rates)

            # Rename cột đúng chuẩn chữ thường (MT5 trả về snake_case sẵn)
            df.rename(columns={
                "time":        "time",
                "open":        "open",
                "high":        "high",
                "low":         "low",
                "close":       "close",
                "tick_volume": "tick_volume",
            }, inplace=True)

            # --- Tầng 5b: Validate cột bắt buộc ---
            missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
            if missing:
                system_logger.error(
                    f"MT5DataPipeline.fetch_data | DataFrame thiếu cột: {missing} "
                    f"— Symbol: {symbol} | TF: {timeframe}"
                )
                return None

            # Chỉ giữ cột cần thiết — bỏ spread, real_volume
            df = df[REQUIRED_COLUMNS].copy()

            # --- Tầng 5c: Convert cột time sang datetime UTC (timezone-aware) ---
            # MT5 trả về Unix timestamp (giây, UTC tuyệt đối)
            # utc=True đảm bảo dtype = datetime64[ns, UTC] — không bị DST bug
            df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

            # --- Tầng 5d: Validate dữ liệu ---
            if len(df) < limit * 0.5:
                # Nếu nhận về ít hơn 50% số nến yêu cầu — cảnh báo nhưng vẫn trả về
                system_logger.warning(
                    f"MT5DataPipeline.fetch_data | Nhận được ít data hơn mong đợi: "
                    f"{len(df)}/{limit} nến — Symbol: {symbol} | TF: {timeframe}"
                )

            # --- Lưu vào cache ---
            self._set_cache(symbol, timeframe, limit, df)

            system_logger.info(
                f"MT5DataPipeline.fetch_data | ✅ Kéo thành công — "
                f"Symbol: {symbol} | TF: {timeframe} | "
                f"Rows: {len(df)} | Từ: {df['time'].iloc[-1]} → {df['time'].iloc[0]}"
            )

            return df

        # Hết retry
        system_logger.error(
            f"MT5DataPipeline.fetch_data | ❌ Tất cả {MAX_RETRY_ATTEMPTS} lần thử thất bại — "
            f"Symbol: {symbol} | TF: {timeframe}. Trả về None."
        )
        return None

    def disconnect(self) -> None:
        """
        Đóng kết nối MT5 và giải phóng tài nguyên terminal.

        Luôn gọi hàm này khi tắt bot để tránh zombie IPC connection.
        """
        if self._is_connected:
            mt5.shutdown()
            self._is_connected = False
            self._cache.clear()
            self._cache_timestamps.clear()
            system_logger.info(
                "MT5DataPipeline.disconnect | 🔌 Kết nối MT5 đã đóng sạch. Cache đã xóa."
            )
        else:
            system_logger.info(
                "MT5DataPipeline.disconnect | Pipeline chưa kết nối — không cần shutdown."
            )

    # ----------------------------------------------------------
    # PRIVATE HELPERS
    # ----------------------------------------------------------

    def _cache_key(self, symbol: str, timeframe: int, limit: int) -> str:
        """Tạo key duy nhất cho cache entry."""
        return f"{symbol}_{timeframe}_{limit}"

    def _get_from_cache(
        self,
        symbol: str,
        timeframe: int,
        limit: int
    ) -> pd.DataFrame | None:
        """
        Lấy data từ cache nếu còn trong TTL.

        Returns:
            pd.DataFrame (copy): Nếu cache còn hạn.
            None               : Nếu cache hết hạn hoặc chưa có.
        """
        key = self._cache_key(symbol, timeframe, limit)
        ttl = CACHE_TTL.get(timeframe, 60)
        now = time.monotonic()

        if key in self._cache:
            age = now - self._cache_timestamps.get(key, 0)
            if age < ttl:
                system_logger.debug(
                    f"MT5DataPipeline | CACHE HIT — {key} | "
                    f"Tuổi cache: {age:.1f}s / TTL: {ttl}s"
                )
                # Trả về copy để tránh mutation bug từ caller
                return self._cache[key].copy()
            else:
                system_logger.debug(
                    f"MT5DataPipeline | CACHE EXPIRED — {key} | "
                    f"Tuổi: {age:.1f}s > TTL: {ttl}s — kéo data mới."
                )

        return None

    def _set_cache(
        self,
        symbol: str,
        timeframe: int,
        limit: int,
        df: pd.DataFrame
    ) -> None:
        """Ghi df vào cache cùng timestamp hiện tại."""
        key = self._cache_key(symbol, timeframe, limit)
        self._cache[key] = df.copy()
        self._cache_timestamps[key] = time.monotonic()

    def _wait_before_retry(self, attempt: int) -> None:
        """
        Chờ trước khi retry. Dùng exponential back-off nhẹ:
            lần 1 → 2s, lần 2 → 4s, lần 3+ → 4s (capped)
        """
        delay = min(RETRY_DELAY_SECONDS * attempt, 4.0)
        system_logger.info(
            f"MT5DataPipeline | Chờ {delay:.0f}s trước lần retry tiếp theo..."
        )
        time.sleep(delay)


# ============================================================
# SMOKE TEST NHANH (chạy trực tiếp: python -m core.data_pipeline)
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Smoke Test: MT5DataPipeline")
    print("=" * 60)

    pipeline = MT5DataPipeline()

    print("\n[1] Thử kết nối MT5...")
    connected = pipeline.connect()

    if connected:
        print("\n[2] Kéo data M5 (100 nến)...")
        df_m5 = pipeline.fetch_data(SYMBOL, TIMEFRAME_M5, CANDLE_COUNT_M5)
        if df_m5 is not None:
            print(f"    ✅ M5 OK — {len(df_m5)} rows | Cột: {list(df_m5.columns)}")
            print(f"    Nến mới nhất: {df_m5['time'].iloc[0]}")
            print(df_m5.head(3).to_string(index=False))

        print("\n[3] Kéo lại M5 (lần 2 — nên từ CACHE)...")
        df_m5_cached = pipeline.fetch_data(SYMBOL, TIMEFRAME_M5, CANDLE_COUNT_M5)
        print(f"    Cache hit: {'✅ YES' if df_m5_cached is not None else '❌ NO'}")

        print("\n[4] Kéo data M15 (200 nến)...")
        df_m15 = pipeline.fetch_data(SYMBOL, TIMEFRAME_M15, CANDLE_COUNT_M15)
        if df_m15 is not None:
            print(f"    ✅ M15 OK — {len(df_m15)} rows")

        print("\n[5] Kéo data H1 (200 nến)...")
        df_h1 = pipeline.fetch_data(SYMBOL, TIMEFRAME_H1, CANDLE_COUNT_H1)
        if df_h1 is not None:
            print(f"    ✅ H1 OK — {len(df_h1)} rows")

        pipeline.disconnect()
        print("\n[6] ✅ Disconnect thành công.")
    else:
        print("\n❌ Kết nối thất bại — xem logs/system.log để biết chi tiết.")

    print("=" * 60)

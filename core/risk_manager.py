"""
core/risk_manager.py — Module Quản trị Rủi ro Rabit_FTMO AI

Chức năng:
    1. Theo dõi và lưu trữ Balance đầu ngày CE(S)T (Start-Of-Day Balance).
    2. Hard-Stop 4.5%: So sánh Equity hiện tại với SOD Balance — khóa bot nếu
       vi phạm Daily Drawdown theo quy tắc FTMO Normal Account.
    3. Position Sizing: Tính Lot Size chuẩn xác cho XAGUSD dựa trên công thức
       tick_value / tick_size từ mt5.symbol_info() — live data, không hardcode.

Kiến trúc:
    class RiskManager
        load_or_init_daily_state(current_balance) -> float   [SOD Balance]
        check_hard_stop(current_equity)            -> bool   [True = khóa bot]
        calculate_lot_size(sl_points, equity)      -> float  [Lot chuẩn]
        _get_cest_today()                          -> str    [private]
        _read_daily_state()                        -> dict   [private]
        _write_daily_state(date, balance)          -> None   [private]

Phase: 2 — Task 2.1

Phụ thuộc:
    - MetaTrader5  >= 5.0.45
    - pytz         >= 2023.3
    - python-dotenv (gián tiếp qua settings)

Tác giả    : Antigravity (AI Coder)
TechLead   : Đã duyệt — 2026-03-05
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5
import pytz

from config.settings import (
    MAX_DAILY_DRAWDOWN,
    RISK_PER_TRADE,
    SYMBOL,
    LOG_DIR,
)
from utils.logger import system_logger


# ============================================================
# CONSTANTS
# ============================================================

# Múi giờ chính thức của FTMO — Prague/Vienna (CE(S)T)
# Tự động handle DST (mùa hè UTC+2, mùa đông UTC+1)
_CEST_TZ = pytz.timezone("Europe/Prague")

# File lưu trạng thái Balance đầu ngày (persist qua crash/restart)
_DAILY_STATE_FILE = Path(LOG_DIR) / "daily_state.json"

# Ngưỡng cảnh báo sớm — từ chối mở lệnh mới khi drawdown vượt 80% giới hạn
# Ví dụ: 4.5% * 0.80 = 3.6% → cảnh báo sớm trước khi chạm hard stop
_EARLY_WARNING_THRESHOLD = MAX_DAILY_DRAWDOWN * 0.80


# ============================================================
# CLASS RiskManager
# ============================================================

class RiskManager:
    """
    Bộ quản trị rủi ro cho tài khoản FTMO Normal Account.

    Bảo vệ tài khoản bằng 2 cơ chế chính:
    1. Hard-Stop 4.5% Daily Drawdown — so sánh Equity vs SOD Balance.
    2. Position Sizing — tính Lot Size dựa trên % rủi ro và khoảng SL.

    Sử dụng:
        risk_mgr = RiskManager(symbol="XAGUSD")
        sod_bal  = risk_mgr.load_or_init_daily_state(current_balance=100000.0)

        # Mỗi chu kỳ:
        if risk_mgr.check_hard_stop(current_equity=95000.0):
            # Đóng lệnh khẩn cấp + dừng bot
            ...

        lot = risk_mgr.calculate_lot_size(
            sl_distance_points=200,
            current_equity=100000.0
        )

    Attributes:
        symbol       (str)        : Symbol giao dịch (XAGUSD).
        _sod_balance (float|None) : Balance đầu ngày CE(S)T đang cache.
        _symbol_info              : mt5.SymbolInfo object — cache để tránh
                                    gọi MT5 mỗi tick.
    """

    def __init__(self, symbol: str = SYMBOL) -> None:
        """
        Khởi tạo RiskManager.

        Args:
            symbol (str): Tên symbol (mặc định lấy từ settings.SYMBOL = "XAGUSD").
        """
        self.symbol: str = symbol
        self._sod_balance: float | None = None
        self._symbol_info = None  # Cache mt5.symbol_info() — load khi cần

        # Đảm bảo thư mục logs/ tồn tại (tạo nếu chưa có)
        _DAILY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

        system_logger.info(
            f"RiskManager | Khởi tạo xong — Symbol: {self.symbol} | "
            f"MAX_DAILY_DRAWDOWN: {MAX_DAILY_DRAWDOWN * 100:.1f}% | "
            f"RISK_PER_TRADE: {RISK_PER_TRADE * 100:.2f}%"
        )

    # ----------------------------------------------------------
    # PUBLIC API
    # ----------------------------------------------------------

    def load_or_init_daily_state(self, current_balance: float) -> float:
        """
        Đọc hoặc khởi tạo SOD Balance (Start-of-Day Balance) theo CE(S)T.

        Logic:
            - Nếu file logs/daily_state.json chưa tồn tại → tạo mới với
              current_balance làm SOD Balance.
            - Nếu file tồn tại nhưng sod_date != ngày CE(S)T hôm nay →
              ngày mới bắt đầu → reset với current_balance mới.
            - Nếu file tồn tại và sod_date == hôm nay → dùng sod_balance
              trong file (consistency sau restart/crash).

        Args:
            current_balance (float): Balance thực tế hiện tại từ mt5.account_info().

        Returns:
            float: SOD Balance — mốc để tính Daily Drawdown.

        Raises:
            SystemExit: Nếu đọc file JSON bị lỗi nghiêm trọng (file hỏng,
                        quyền truy cập) → dừng bot ngay, không đoán mò SOD Balance.
        """
        today_cest = self._get_cest_today()
        existing = self._read_daily_state()  # có thể raise SystemExit nếu lỗi critical

        if existing is None or existing.get("sod_date") != today_cest:
            # --- Trường hợp 1: File chưa có HOẶC ngày mới ---
            action = "Khởi tạo lần đầu" if existing is None else f"Reset ngày mới (trước: {existing.get('sod_date', 'N/A')})"
            self._write_daily_state(date=today_cest, balance=current_balance)
            self._sod_balance = current_balance
            system_logger.info(
                f"RiskManager.load_or_init_daily_state | [{action}] "
                f"SOD Balance = {current_balance:,.2f} | Ngày CE(S)T: {today_cest}"
            )
        else:
            # --- Trường hợp 2: Cùng ngày → dùng balance đã lưu ---
            self._sod_balance = existing["sod_balance"]
            system_logger.info(
                f"RiskManager.load_or_init_daily_state | Đọc từ file (cùng ngày CE(S)T: {today_cest}) "
                f"SOD Balance = {self._sod_balance:,.2f} "
                f"(Balance hiện tại: {current_balance:,.2f})"
            )

        return self._sod_balance

    def check_hard_stop(self, current_equity: float) -> bool:
        """
        Kiểm tra Hard-Stop: Bot có vi phạm Daily Drawdown 4.5% không?

        Công thức FTMO:
            drawdown_pct = (SOD_Balance - current_equity) / SOD_Balance
            Nếu drawdown_pct >= MAX_DAILY_DRAWDOWN (0.045) → KHÓA BOT

        Args:
            current_equity (float): Equity thực tế hiện tại (balance + unrealized P&L).

        Returns:
            bool:
                True  → Vi phạm — Bot PHẢI dừng, đóng toàn bộ lệnh ngay lập tức.
                False → An toàn — Bot tiếp tục hoạt động bình thường.

        Side-effects:
            - Log CRITICAL nếu vi phạm Hard-Stop 4.5%.
            - Log WARNING nếu đến ngưỡng cảnh báo sớm 80% (3.6%).
        """
        if self._sod_balance is None:
            system_logger.error(
                "RiskManager.check_hard_stop | SOD Balance chưa được khởi tạo! "
                "Gọi load_or_init_daily_state() trước khi check_hard_stop(). "
                "Trả về True (an toàn nhất — khóa bot để bảo vệ tài khoản)."
            )
            return True  # Fail-safe: nếu không có SOD Balance → khóa bot

        drawdown_pct = (self._sod_balance - current_equity) / self._sod_balance
        drawdown_usd = self._sod_balance - current_equity

        # --- Hard Stop: vi phạm FTMO ---
        if drawdown_pct >= MAX_DAILY_DRAWDOWN:
            system_logger.critical(
                f"RiskManager.check_hard_stop | ⛔ HARD STOP TRIGGERED! "
                f"Daily Drawdown vi phạm FTMO! "
                f"SOD Balance: {self._sod_balance:,.2f} | "
                f"Equity hiện tại: {current_equity:,.2f} | "
                f"Lỗ trong ngày: -{drawdown_usd:,.2f} ({drawdown_pct * 100:.2f}%) "
                f"≥ Giới hạn {MAX_DAILY_DRAWDOWN * 100:.1f}% — BOT DỪNG NGAY!"
            )
            return True  # KHÓA BOT

        # --- Early Warning: cảnh báo sớm (80% ngưỡng) ---
        if drawdown_pct >= _EARLY_WARNING_THRESHOLD:
            system_logger.warning(
                f"RiskManager.check_hard_stop | ⚠️ CẢNH BÁO SỚM! "
                f"Drawdown đang ở {drawdown_pct * 100:.2f}% "
                f"(Ngưỡng cảnh báo: {_EARLY_WARNING_THRESHOLD * 100:.2f}% | "
                f"Hard Stop: {MAX_DAILY_DRAWDOWN * 100:.1f}%). "
                f"Lỗ: -{drawdown_usd:,.2f} — Cân nhắc DỪNG vào lệnh mới."
            )

        # --- An toàn ---
        system_logger.debug(
            f"RiskManager.check_hard_stop | ✅ An toàn — "
            f"Drawdown: {drawdown_pct * 100:.2f}% / {MAX_DAILY_DRAWDOWN * 100:.1f}% | "
            f"Equity: {current_equity:,.2f} | SOD: {self._sod_balance:,.2f}"
        )
        return False  # TIẾP TỤC

    def calculate_lot_size(
        self,
        sl_distance_points: float,
        current_equity: float,
    ) -> float:
        """
        Tính Lot Size chuẩn xác để rủi ro đúng RISK_PER_TRADE% nếu dính SL.

        Công thức:
            risk_amount       = current_equity × RISK_PER_TRADE
            value_per_point   = tick_value / tick_size × point   [USD/point/lot]
            raw_lot           = risk_amount / (sl_distance_points × value_per_point)
            lot_size          = clamp(raw_lot, vol_min, vol_max, vol_step)

        Args:
            sl_distance_points (float): Khoảng cách SL tính bằng points (digits).
                                        Ví dụ: SL = 0.200 USD → sl_distance_points = 200.
            current_equity     (float): Equity hiện tại của tài khoản (USD).

        Returns:
            float: Lot Size đã làm tròn và clamp theo quy định của sàn.
                   Trả về 0.0 nếu có lỗi (không lấy được symbol_info).

        Notes:
            - Hàm tự động lấy symbol_info từ MT5 khi cần (cache lại sau lần đầu).
            - Nếu raw_lot bị clamp (vượt min/max), sẽ log WARNING để TechLead biết.
        """
        # --- Validate input ---
        if sl_distance_points <= 0:
            system_logger.error(
                f"RiskManager.calculate_lot_size | sl_distance_points phải > 0. "
                f"Nhận được: {sl_distance_points}. Trả về 0.0."
            )
            return 0.0

        if current_equity <= 0:
            system_logger.error(
                f"RiskManager.calculate_lot_size | current_equity phải > 0. "
                f"Nhận được: {current_equity}. Trả về 0.0."
            )
            return 0.0

        # --- Lấy Symbol Info từ MT5 (cache) ---
        symbol_info = self._get_symbol_info()
        if symbol_info is None:
            return 0.0

        # --- Bóc tách thông số từ Symbol Info ---
        tick_value: float = symbol_info.trade_tick_value  # USD/tick/lot
        tick_size:  float = symbol_info.trade_tick_size   # Kích thước 1 tick
        point:      float = symbol_info.point             # Giá trị 1 point
        vol_min:    float = symbol_info.volume_min        # Lot tối thiểu
        vol_max:    float = symbol_info.volume_max        # Lot tối đa
        vol_step:   float = symbol_info.volume_step       # Bước làm tròn lot

        # --- Tính giá trị mỗi point di chuyển (1 Lot, tính bằng USD) ---
        # Lý do dùng tick_value/tick_size: MT5 đã quy đổi về đơn vị tài khoản (USD)
        # kể cả khi rate ngoại tệ thay đổi. An toàn hơn dùng contract_size thủ công.
        value_per_point_per_lot: float = (tick_value / tick_size) * point

        if value_per_point_per_lot <= 0:
            system_logger.error(
                f"RiskManager.calculate_lot_size | value_per_point_per_lot = "
                f"{value_per_point_per_lot:.6f} ≤ 0 — tick_value hoặc tick_size "
                f"bất thường. Trả về 0.0."
            )
            return 0.0

        # --- Tính số tiền chấp nhận lỗ ---
        risk_amount: float = current_equity * RISK_PER_TRADE

        # --- Tính raw lot ---
        raw_lot: float = risk_amount / (sl_distance_points * value_per_point_per_lot)

        # --- Clamp theo giới hạn sàn ---
        clamped = False

        if raw_lot > vol_max:
            system_logger.warning(
                f"RiskManager.calculate_lot_size | ⚠️ Raw Lot {raw_lot:.4f} vượt "
                f"vol_max {vol_max:.2f} — Bị cap tại {vol_max:.2f}. "
                f"SL có thể quá gần hoặc equity quá lớn cho 1 lệnh."
            )
            raw_lot = vol_max
            clamped = True

        if raw_lot < vol_min:
            system_logger.warning(
                f"RiskManager.calculate_lot_size | ⚠️ Raw Lot {raw_lot:.4f} dưới "
                f"vol_min {vol_min:.2f} — Nâng lên {vol_min:.2f}. "
                f"Equity quá nhỏ hoặc SL quá xa."
            )
            raw_lot = vol_min
            clamped = True

        # --- Làm tròn theo vol_step (ví dụ: step=0.01 → 0.56789 → 0.57) ---
        lot_size: float = round(raw_lot / vol_step) * vol_step
        # Làm tròn thêm 2 chữ số để tránh floating point noise (0.010000000001)
        lot_size = round(lot_size, 2)

        # --- Log kết quả ---
        system_logger.info(
            f"RiskManager.calculate_lot_size | "
            f"Equity: {current_equity:,.2f} | "
            f"Risk: {RISK_PER_TRADE * 100:.2f}% = ${risk_amount:,.2f} | "
            f"SL: {sl_distance_points} pts | "
            f"Val/pt/lot: ${value_per_point_per_lot:.4f} | "
            f"Raw Lot: {raw_lot:.4f} | "
            f"{'⚠️ CLAMPED → ' if clamped else ''}"
            f"Final Lot: {lot_size:.2f}"
        )

        return lot_size

    # ----------------------------------------------------------
    # PRIVATE HELPERS
    # ----------------------------------------------------------

    def _get_cest_today(self) -> str:
        """
        Trả về ngày hiện tại theo múi giờ CE(S)T dạng 'YYYY-MM-DD'.

        CE(S)T = Central European (Summer) Time = múi giờ của FTMO (Prague).
        Tự động xử lý DST:
            - Mùa đông (CET):  UTC+1
            - Mùa hè (CEST):   UTC+2

        Returns:
            str: Ví dụ '2026-03-05'
        """
        now_utc = datetime.now(tz=pytz.utc)
        now_cest = now_utc.astimezone(_CEST_TZ)
        return now_cest.strftime("%Y-%m-%d")

    def _read_daily_state(self) -> dict | None:
        """
        Đọc file logs/daily_state.json.

        Returns:
            dict: Nội dung file JSON nếu đọc thành công.
            None: Nếu file chưa tồn tại (trường hợp bình thường — ngày đầu tiên).

        Raises:
            SystemExit: Nếu file tồn tại nhưng bị hỏng (JSON decode error)
                        hoặc lỗi quyền truy cập (PermissionError, OSError).
                        Dừng bot ngay — không đoán mò SOD Balance.
        """
        if not _DAILY_STATE_FILE.exists():
            # File chưa tồn tại — trường hợp bình thường (lần đầu chạy)
            return None

        try:
            with open(_DAILY_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validate cấu trúc file — phòng trường hợp file bị ghi sai
            required_keys = {"sod_date", "sod_balance", "recorded_at_utc"}
            missing = required_keys - set(data.keys())
            if missing:
                raise ValueError(f"File thiếu các key bắt buộc: {missing}")

            if not isinstance(data["sod_balance"], (int, float)):
                raise ValueError(
                    f"sod_balance phải là số, nhận được: {type(data['sod_balance'])}"
                )

            return data

        except json.JSONDecodeError as e:
            system_logger.critical(
                f"RiskManager._read_daily_state | ❌ CRITICAL: File JSON bị hỏng: "
                f"{_DAILY_STATE_FILE} — Lỗi: {e}. "
                "Bot dừng ngay để bảo vệ tài khoản. "
                "Xóa file này thủ công để Bot có thể khởi động lại."
            )
            sys.exit(1)  # Hard exit — không thể đoán mò SOD Balance

        except (ValueError, PermissionError, OSError) as e:
            system_logger.critical(
                f"RiskManager._read_daily_state | ❌ CRITICAL: Không thể đọc "
                f"{_DAILY_STATE_FILE} — Lỗi: {type(e).__name__}: {e}. "
                "Bot dừng ngay để bảo vệ tài khoản."
            )
            sys.exit(1)  # Hard exit

    def _write_daily_state(self, date: str, balance: float) -> None:
        """
        Ghi SOD Balance vào file logs/daily_state.json.

        Args:
            date    (str)  : Ngày CE(S)T dạng 'YYYY-MM-DD'.
            balance (float): SOD Balance cần lưu.

        Raises:
            SystemExit: Nếu không thể ghi file (PermissionError, DiskFull, etc.).
                        SOD Balance không được lưu → không thể bảo vệ tài khoản
                        → dừng bot ngay.
        """
        now_utc = datetime.now(tz=pytz.utc)
        payload = {
            "sod_date":       date,
            "sod_balance":    round(balance, 2),
            "recorded_at_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        try:
            with open(_DAILY_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            system_logger.info(
                f"RiskManager._write_daily_state | ✅ Đã ghi SOD Balance: "
                f"{balance:,.2f} | Ngày CE(S)T: {date} | "
                f"File: {_DAILY_STATE_FILE}"
            )

        except (PermissionError, OSError) as e:
            system_logger.critical(
                f"RiskManager._write_daily_state | ❌ CRITICAL: Không thể ghi file "
                f"{_DAILY_STATE_FILE} — Lỗi: {type(e).__name__}: {e}. "
                "SOD Balance không được lưu → Bot dừng để bảo vệ tài khoản."
            )
            sys.exit(1)  # Hard exit

    def _get_symbol_info(self):
        """
        Lấy mt5.SymbolInfo cho symbol (có cache).

        Cache lại sau lần đầu để tránh spam MT5 API mỗi tick.
        Tự động refresh nếu MT5 trả về None.

        Returns:
            mt5.SymbolInfo | None: None nếu MT5 không kết nối hoặc symbol không tồn tại.
        """
        if self._symbol_info is not None:
            return self._symbol_info

        info = mt5.symbol_info(self.symbol)

        if info is None:
            err = mt5.last_error()
            system_logger.error(
                f"RiskManager._get_symbol_info | mt5.symbol_info('{self.symbol}') "
                f"trả về None — Lỗi MT5: {err}. "
                "Kiểm tra symbol có trong Market Watch và MT5 đang kết nối không."
            )
            return None

        self._symbol_info = info
        system_logger.info(
            f"RiskManager._get_symbol_info | ✅ Symbol Info loaded: "
            f"{self.symbol} | "
            f"tick_value={info.trade_tick_value} | "
            f"tick_size={info.trade_tick_size} | "
            f"point={info.point} | "
            f"vol_min={info.volume_min} | vol_max={info.volume_max} | "
            f"vol_step={info.volume_step}"
        )
        return self._symbol_info

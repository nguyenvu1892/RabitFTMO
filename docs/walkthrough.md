# docs/walkthrough.md — Phân tích Kỹ thuật: Risk Management Module

**Phase 2 — Task 2.1**
**Branch:** `feature/phase2-risk-management`
**Author:** Antigravity (AI Coder)
**Date:** 2026-03-05
**Status:** 🟡 PENDING TechLead Review

---

## Mục Lục

1. [Phân tích Luật Daily Drawdown của FTMO](#1-phân-tích-luật-daily-drawdown-của-ftmo)
2. [Bài toán: Bot Python biết Balance đầu ngày bằng cách nào?](#2-bài-toán-bot-python-biết-balance-đầu-ngày-bằng-cách-nào)
3. [Phân tích Công thức Lot Size XAGUSD trên MT5](#3-phân-tích-công-thức-lot-size-xagusd-trên-mt5)
4. [Kế hoạch Triển khai (Implementation Plan)](#4-kế-hoạch-triển-khai-implementation-plan)
5. [Rủi ro & Biện pháp Giảm thiểu](#5-rủi-ro--biện-pháp-giảm-thiểu)

---

## 1. Phân tích Luật Daily Drawdown của FTMO

### 1.1 Quy tắc chính thức của FTMO

> **FTMO Normal Account — Daily Loss Limit: 5% initial_balance**
> Tài khoản $100,000 → Tổng lỗ trong ngày không được vượt **$5,000**.

**Điểm mấu chốt — cách FTMO tính "đầu ngày":**

| Yếu tố | Chi tiết |
|--------|---------|
| **Mốc thời gian reset** | **00:00 CE(S)T** (Central European Standard/Summer Time) |
| **Múi giờ CE(S)T** | UTC+1 (mùa đông) / UTC+2 (mùa hè) → tương đương ~06:00–07:00 Việt Nam |
| **Cách tính drawdown** | `Daily_Drawdown = Opening_Day_Balance + Floating_PnL_All_Positions − Current_Equity` |
| **Balance "đầu ngày" (SOD Balance)** | Là **Balance tại thời điểm 00:00 CE(S)T**, BẤT KỂ balance hiện tại bao nhiêu |
| **Bao gồm cả vị thế đang mở?** | **CÓ** — Equity (balance + P&L unrealized) được so sánh, không chỉ balance |

**Ví dụ thực tế:**
```
Ngày 1 — 00:00 CEST: Balance = $102,000 (đã kiếm $2,000 hôm qua)
→ SOD_Balance = $102,000
Ngưỡng Hard-Stop = $102,000 × (1 - 0.045) = $97,410

Nếu equity rơi xuống dưới $97,410 → BOT PHẢI DỪNG NGAY
```

**Dự án này dùng 4.5%** (thay vì 5% max của FTMO) theo thiết lập trong `settings.py`:
```python
MAX_DAILY_DRAWDOWN = 0.045  # Buffer an toàn 0.5% so với giới hạn cứng FTMO 5%
```

---

## 2. Bài toán: Bot Python biết Balance đầu ngày bằng cách nào?

### 2.1 Thách thức

**Vấn đề cốt lõi:** MT5 **không cung cấp API trực tiếp** cho "Balance tại 00:00 CE(S)T".
`mt5.account_info().balance` chỉ trả về balance *hiện tại* (real-time), không lưu mốc đầu ngày.

### 2.2 Phân tích các Giải pháp

#### ❌ Giải pháp 1 — Lấy từ `mt5.account_info()` trực tiếp
```python
# KHÔNG DÙNG ĐƯỢC cho mục đích này
balance_now = mt5.account_info().balance  # Thay đổi liên tục theo từng lệnh đóng
```
**Vấn đề:** Balance hiện tại không phải balance đầu ngày — không tuân thủ luật FTMO.

#### ⚠️ Giải pháp 2 — Lấy từ lịch sử giao dịch MT5 (Phức tạp)
```python
# mt5.history_deals_get() → duyệt toàn bộ lịch sử giao dịch trong ngày
# → Tìm balance tại mốc 00:00 CE(S)T
```
**Vấn đề:** Phức tạp, tốn tài nguyên, cần xử lý timezone CE(S)T.

#### ✅ Giải pháp 3 — File-based Persistence (ĐƯỢC CHỌN — Đơn giản, Chắc chắn)
**Cơ chế:**
1. Khi Bot khởi động lần đầu mỗi ngày CE(S)T → **ghi `sod_balance` và `sod_date` vào file JSON**.
2. Mỗi chu kỳ tiếp theo → **đọc file JSON** để so sánh equity với SOD Balance.
3. Mỗi khi ngày CE(S)T mới bắt đầu → **tự động reset** file JSON với balance mới.

```python
# Cấu trúc file: logs/daily_state.json
{
    "sod_date": "2026-03-05",        # Ngày CE(S)T hiện tại
    "sod_balance": 102345.67,        # Balance lúc bot khởi động đầu ngày
    "recorded_at_utc": "2026-03-05T05:00:00Z"  # Timestamp thực lúc ghi
}
```

**Tại sao File JSON thay vì Database/Memory?**
- **Persistence sau crash/restart:** Bot crash rồi restart vẫn nhớ SOD Balance — **quan trọng nhất**.
- **Audit trail:** TechLead có thể kiểm tra thủ công bất kỳ lúc nào.
- **Zero dependency:** Không cần thêm thư viện, không cần DB server.

**Logic xác định "đầu ngày mới" (CE(S)T):**
```python
import pytz
from datetime import datetime

CEST_TZ = pytz.timezone("Europe/Prague")  # Múi giờ FTMO chính thức

def _get_cest_today() -> str:
    """Trả về ngày hiện tại theo CE(S)T dạng 'YYYY-MM-DD'."""
    now_utc = datetime.utcnow().replace(tzinfo=pytz.utc)
    now_cest = now_utc.astimezone(CEST_TZ)
    return now_cest.strftime("%Y-%m-%d")
```

---

## 3. Phân tích Công thức Lot Size XAGUSD trên MT5

### 3.1 Đặc điểm của XAGUSD (Silver/USD) trên MT5 FTMO

XAGUSD là **CFD kim loại quý**, không phải Forex thuần túy. Điều này ảnh hưởng lớn đến cách tính lot.

**Các thông số cần lấy từ `mt5.symbol_info("XAGUSD")`:**

| Tham số | Tên trong MT5 | Giá trị điển hình | Ý nghĩa |
|---------|--------------|-------------------|---------|
| `trade_contract_size` | Contract size | **5000** oz/lot | 1 Lot = 5,000 oz bạc |
| `trade_tick_size` | Tick size | **0.001** | Biến động nhỏ nhất = 0.001 USD/oz |
| `trade_tick_value` | Tick value | **5.0** USD | Mỗi tick di chuyển → lãi/lỗ $5.0 |
| `digits` | Digits | **3** | 3 chữ số thập phân (vd: 32.105) |
| `volume_min` | Min Lot | **0.01** | Lệnh nhỏ nhất = 0.01 Lot |
| `volume_max` | Max Lot | **50.0** | Lệnh lớn nhất = 50.0 Lot |
| `volume_step` | Lot step | **0.01** | Bước tăng/giảm Lot |

### 3.2 Hai Phương pháp Tính Lot — Phân tích So sánh

#### Phương pháp A — Dùng `tick_value` và `tick_size` (ĐƯỢC CHỌN ✅)

**Công thức cơ sở:**
```
Pip_Value_Per_Lot = (trade_tick_value / trade_tick_size) × point_size

Lot_Size = (Equity × Risk%) / (SL_distance_points × Pip_Value_Per_Lot)
```

**Triển khai cụ thể cho XAGUSD:**
```python
# Lấy từ mt5.symbol_info()
tick_value = symbol_info.trade_tick_value  # VD: 5.0 USD/tick
tick_size  = symbol_info.trade_tick_size   # VD: 0.001

# Giá trị mỗi point (= 1 digit) di chuyển, tính theo USD, cho 1 Lot
point = symbol_info.point                 # = 0.001 cho XAGUSD (digits=3)
value_per_point_per_lot = tick_value / tick_size * point
# = 5.0 / 0.001 * 0.001 = 5.0 USD mỗi point, 1 Lot

# Số tiền chấp nhận lỗ (risk amount)
risk_amount = equity * RISK_PER_TRADE       # VD: $102,000 × 0.5% = $510

# Tính lot
raw_lot = risk_amount / (sl_distance_points * value_per_point_per_lot)

# Làm tròn theo volume_step
lot_step = symbol_info.volume_step          # VD: 0.01
lot_size = round(raw_lot / lot_step) * lot_step
```

**Ví dụ số học:**
```
Equity        = $100,000
RISK_PER_TRADE= 0.5%   → Risk Amount = $500
SL Distance   = 200 points (= 0.200 USD trên XAGUSD)

tick_value    = 5.0 USD, tick_size = 0.001, point = 0.001
value_per_pt  = 5.0 / 0.001 × 0.001 = 5.0 USD/point/lot

raw_lot = $500 / (200 × 5.0) = $500 / $1,000 = 0.50 Lot

Kiểm tra: 0.50 Lot × 200 points × 5.0 USD/point = $500 ✅
```

#### Phương pháp B — Dùng `contract_size` (Tham chiếu thêm)

```
Dollar_Per_Point_Per_Lot = contract_size × point / account_currency_rate
Lot = risk_amount / (sl_points × dollar_per_point)
```

**Vì sao KHÔNG chọn phương pháp B?**
Phương pháp B yêu cầu lấy tỷ giá quy đổi nếu Base Currency không phải USD. Trong trường hợp XAGUSD, quote currency là USD nên đơn giản hơn — nhưng `tick_value` từ MT5 **đã tự động tính sẵn trong đơn vị tiền tệ của tài khoản** (USD), bao gồm cả mọi quy đổi. Dùng `tick_value` an toàn hơn và ít hardcode hơn.

### 3.3 Ràng buộc Min/Max Lot

```python
# Clamp theo giới hạn sàn — BẮT BUỘC
lot_size = max(symbol_info.volume_min, lot_size)   # Tối thiểu 0.01
lot_size = min(symbol_info.volume_max, lot_size)   # Tối đa 50.0
lot_size = round(lot_size / lot_step) * lot_step   # Làm tròn step

# Cảnh báo nếu bị clamp
if raw_lot > symbol_info.volume_max:
    logger.warning(f"Lot bị cap tại max {symbol_info.volume_max} — SL quá gần?")
if raw_lot < symbol_info.volume_min:
    logger.warning(f"Lot bị cap tại min {symbol_info.volume_min} — Equity quá nhỏ hoặc SL quá xa?")
```

---

## 4. Kế hoạch Triển khai (Implementation Plan)

### 4.1 Cấu trúc Class `RiskManager`

```
core/risk_manager.py
└── class RiskManager
    ├── __init__(symbol_info, logger)
    ├── load_or_init_daily_state(current_balance) → float  [SOD Balance]
    ├── check_hard_stop(current_equity)           → bool   [True = khóa bot]
    └── calculate_lot_size(sl_distance_points, current_equity) → float
```

### 4.2 Chi tiết từng Hàm

#### `load_or_init_daily_state(current_balance) → float`
- Đọc file `logs/daily_state.json`.
- Nếu file không tồn tại HOẶC `sod_date` khác ngày CE(S)T hiện tại → ghi file mới với `current_balance`.
- Trả về `sod_balance` (luôn là balance đầu ngày CE(S)T).

#### `check_hard_stop(current_equity) → bool`
```
drawdown_pct = (sod_balance - current_equity) / sod_balance
if drawdown_pct >= MAX_DAILY_DRAWDOWN:
    CRITICAL log
    return True  # Khóa bot
return False
```

#### `calculate_lot_size(sl_distance_points, current_equity) → float`
```
risk_amount = current_equity × RISK_PER_TRADE
value_per_pt = tick_value / tick_size × point
raw_lot = risk_amount / (sl_distance_points × value_per_pt)
lot_size = clamp(raw_lot, vol_min, vol_max, vol_step)
return lot_size
```

### 4.3 Dependency & Import

```python
# core/risk_manager.py sẽ import từ:
from config.settings import (
    RISK_PER_TRADE,       # 0.005
    MAX_DAILY_DRAWDOWN,   # 0.045
)
from utils.logger import system_logger, trade_logger
import MetaTrader5 as mt5
import json
import pytz
from datetime import datetime
from pathlib import Path
```

### 4.4 Tích hợp vào Vòng lặp Chính (main.py — Phase 2)

```python
# Khởi động bot:
risk_manager = RiskManager(symbol="XAGUSD")
sod_balance = risk_manager.load_or_init_daily_state(current_balance)

# Mỗi chu kỳ (vd: mỗi 5 giây):
account = pipeline.get_account_info()
if risk_manager.check_hard_stop(account["equity"]):
    logger.critical("HARD STOP TRIGGERED — BOT ĐÓNG TOÀN BỘ VỊ THẾ VÀ DỪNG")
    # → Gọi hàm đóng lệnh khẩn cấp
    break

# Trước khi đặt lệnh:
lot = risk_manager.calculate_lot_size(
    sl_distance_points=sl_pts,
    current_equity=account["equity"]
)
```

---

## 5. Rủi ro & Biện pháp Giảm thiểu

### 5.1 Slippage Risk — Lỗ Vượt 4.5%

> **Câu hỏi:** Slippage có thể làm khoản lỗ thực tế vượt mức 4.5% không?

**Câu trả lời: CÓ — và đây là rủi ro thực tế.**

| Kịch bản | Chi tiết |
|---------|---------|
| **Slippage thị trường** | Tin tức đột ngột (NFP, Fed) → giá nhảy vọt qua SL → lệnh đóng tại giá kém hơn SL |
| **Gap qua cuối tuần** | Thị trường mở cửa thứ Hai với gap lớn → SL không khả dụng |
| **Low liquidity** | XAGUSD kém thanh khoản ngoài giờ London/NY → spread giãn rộng, slippage cao |

**Biện pháp giảm thiểu được thiết kế trong RiskManager:**

1. **Buffer 0.5% trong Hard Stop:** FTMO giới hạn 5% nhưng ta Hard Stop tại 4.5% — tạo bộ đệm $500 cho mỗi $100,000 để hấp thụ slippage.

2. **Pre-trade Check:** Trước khi đặt lệnh MỚI, kiểm tra nếu drawdown hiện tại đã > 4.0% → từ chối mở lệnh mới (ngay cả khi chưa đạt 4.5%).

3. **FORCE_CLOSE_HOUR (22:00 UTC):** Đóng hết lệnh trước 22:00 UTC → tránh gap overnight, slippage phiên châu Á ít thanh khoản.

4. **FRIDAY_CLOSE_HOUR (20:00 UTC):** Đóng hết trước 20:00 UTC thứ Sáu → phòng gap cuối tuần.

5. **ATR-calibrated SL:** SL tính theo ATR nhân hệ số 1.5 → SL không quá chặt, giảm xác suất bị slippage đánh úp.

6. **Max Lot Clamp:** `calculate_lot_size()` cắt cứng tại `volume_max` của sàn → tránh tình huống lỗi tràn tính toán ra lot khổng lồ.

7. **(Nâng cao — Phase 3+):** Implement `max_risk_per_trade_buffer`: Nếu 1 lệnh tính lỗ full SL sẽ làm drawdown > 3.5% → từ chối thêm — chặn "one-shot knockout".

---

## Tóm tắt

| Hạng mục | Quyết định |
|---------|-----------|
| SOD Balance tracking | File JSON persistence — `logs/daily_state.json` |
| Timezone chuẩn | `Europe/Prague` (CE(S)T) — múi giờ FTMO chính thức |
| Công thức Lot Size | `tick_value / tick_size × point` — lấy từ `mt5.symbol_info()` live |
| Hard Stop threshold | 4.5% (buffer 0.5% so với FTMO 5%) |
| Risk per trade | 0.5% equity |
| Slippage protection | 4.5% buffer + Force close 22:00 UTC + ATR SL |

---

*Tài liệu này được viết phục vụ TechLead Review trước khi bắt đầu viết code.*
*Xem xét và gõ "PROCEED" để AI bắt đầu implementation.*
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

---

## Bug Fix — Task 2.1.1: Thiếu khai báo `pytz` trong `requirements.txt`

**Date:** 2026-03-05 | **Commit:** `42cf2aa` | **Branch:** `main` (hotfix)

**Task 2.1.1: Fix ModuleNotFoundError — pytz missing**

* **Nội dung thay đổi/hoạt động:**
  - `requirements.txt` — Thêm dòng `pytz>=2023.3` vào Tầng 2 (Security/Utilities), kèm comment giải thích dùng cho RiskManager tính timezone `Europe/Prague` (CE(S)T).
  - `History.txt` — Ghi log bug fix và note rút kinh nghiệm.

* **Lý do:** `core/risk_manager.py` import `pytz` để xác định ngày CE(S)T (múi giờ FTMO) nhưng thư viện này không có sẵn trong stdlib Python và chưa được khai báo vào `requirements.txt`. Khi người dùng cài môi trường mới từ `pip install -r requirements.txt` sẽ thiếu `pytz` → `ModuleNotFoundError` ngay khi import RiskManager. Lỗi xuất hiện ngay lần chạy đầu tiên sau merge.

* **Đề xuất cải tiến:** Thiết lập CI pre-commit hook chạy `pip check` hoặc `pipreqs --diff` để tự động phát hiện thư viện được import trong code nhưng chưa có trong `requirements.txt` — tránh lặp lại bug tương tự ở các Phase sau.

---
---

# Phase 3 — Task 3.1: Phân tích Thuật toán Strategy Engine

**Branch:** `feature/phase3.1-h1-m15-logic`
**Author:** Antigravity (AI Coder)
**Date:** 2026-03-05
**Status:** 🟡 PENDING TechLead Review — Awaiting "PROCEED" command

---

## Mục Lục

1. [Thuật toán Market Structure H1 — Fractal Anti-Repainting](#1-thuật-toán-market-structure-h1--fractal-anti-repainting)
2. [Thuật toán SMC FVG M15 — 3-Candle Imbalance + Mitigation](#2-thuật-toán-smc-fvg-m15--3-candle-imbalance--mitigation)
3. [Đề xuất Cấu trúc Dữ liệu cho FVG List — Queue hay Deque?](#3-đề-xuất-cấu-trúc-dữ-liệu-cho-fvg-list--queue-hay-deque)
4. [Kế hoạch Tham số hóa — AI Tunable Parameters](#4-kế-hoạch-tham-số-hóa--ai-tunable-parameters)
5. [Rủi ro & Biện pháp Giảm thiểu](#5-rủi-ro--biện-pháp-giảm-thiểu)

---

## 1. Thuật toán Market Structure H1 — Fractal Anti-Repainting

### 1.1 Bài toán cốt lõi: Repainting là gì và tại sao nguy hiểm?

**Repainting** là hiện tượng một chỉ báo hoặc thuật toán vẽ lại tín hiệu quá khứ khi có dữ liệu mới. Đây là **lỗi chết người** trong giao dịch tự động:

| Kịch bản Repainting | Hậu quả |
|---------------------|---------|
| Nến hiện tại (đang hình thành) được dùng làm tham chiếu Fractal | Tín hiệu "mua/bán" thay đổi liên tục trong cùng 1 nến → bot mở lệnh sai |
| Swing High tại nến N được xác nhận bằng nến N+1 cũng đang mở | Khi nến N+1 đóng cửa thấp hơn, Swing High bị hủy → đã lỡ vào lệnh |
| Indicator MT4/MT5 dùng `[0]` (nến hiện tại) | 100% Repainting — chỉ an toàn khi dùng `[2]` trở về trước |

**Nguyên tắc Anti-Repainting tuyệt đối:**
> **CHỈ SỬ DỤNG CÁC NẾN ĐÃ ĐÓNG CỬA HOÀN TOÀN.**
> Trong DataFrame pandas từ MT5, nến hiện tại (đang chạy) là index `-1` (cuối cùng).
> Mọi phép tính Fractal **bắt buộc** dừng tại index `-2` trở về trước (nến đã đóng).

---

### 1.2 Định nghĩa Fractal Swing High / Swing Low

**Fractal chuẩn** (Bill Williams): Một nến trung tâm được gọi là **Swing High** nếu nó có giá `high` cao hơn `N` nến hai bên.

```
Ví dụ với FRACTAL_PERIOD = 2 (dùng 2 nến mỗi bên):

Index:  [i-2]  [i-1]  [i]  [i+1]  [i+2]
High:    30     31    35    32      29
                         ↑
                    SWING HIGH tại [i] nếu:
                    high[i] > high[i-1] AND
                    high[i] > high[i-2] AND
                    high[i] > high[i+1] AND
                    high[i] > high[i+2]
```

**Swing Low** là nghịch đảo — nến giữa có `low` thấp hơn N nến hai bên.

---

### 1.3 Cơ chế Anti-Repainting trong Python/Pandas

```
DataFrame từ MT5 (Cột: time, open, high, low, close, tick_volume):

Index:  0      1      2      3      4    ... n-2    n-1
        (nến cũ nhất)                    (đã đóng) (ĐANG CHẠY)

                                              ↑         ↑
                                     Nến cuối cùng   LOẠI BỎ
                                     đã đóng hoàn   (Repainting)
                                     toàn = safe
```

**Quy tắc triển khai:**
1. Nhận DataFrame `df_h1` với tất cả nến.
2. **CHỈ XỬ LÝ** trên `df_safe = df_h1.iloc[:-1]` — loại bỏ nến cuối đang chạy.
3. Duyệt từ index `FRACTAL_PERIOD` đến `len(df_safe) - FRACTAL_PERIOD - 1`.
4. Kiểm tra điều kiện Fractal tại mỗi nến.

**Pseudocode chi tiết:**
```
FRACTAL_PERIOD = 2  # Tham số (AI có thể tuning: 1, 2, 3)

function is_swing_high(df, i, period):
    center_high = df['high'].iloc[i]
    for j in range(1, period + 1):
        if center_high <= df['high'].iloc[i - j]:  return False
        if center_high <= df['high'].iloc[i + j]:  return False
    return True

function is_swing_low(df, i, period):
    center_low = df['low'].iloc[i]
    for j in range(1, period + 1):
        if center_low >= df['low'].iloc[i - j]:   return False
        if center_low >= df['low'].iloc[i + j]:   return False
    return True
```

---

### 1.4 Xác định Directional Bias — BUY / SELL / NEUTRAL

**Lý thuyết SMC — Market Structure:**
- **BUY bias:** Thị trường tạo **Higher Highs (HH) và Higher Lows (HL)** → xu hướng tăng.
- **SELL bias:** Thị trường tạo **Lower Highs (LH) và Lower Lows (LL)** → xu hướng giảm.
- **NEUTRAL:** Không đủ dữ liệu hoặc thị trường đang sideway.

**Thuật toán xác định bias (dựa trên 2 Swing High và 2 Swing Low gần nhất):**

```
Tìm tất cả Swing High và Swing Low trong df_safe (đã bỏ FRACTAL_PERIOD nến hai đầu)

Lấy 2 Swing High gần nhất: SH_prev, SH_last
Lấy 2 Swing Low gần nhất:  SL_prev, SL_last

Điều kiện BUY:
    (SH_last.high > SH_prev.high) AND   ← Higher High
    (SL_last.low  > SL_prev.low)        ← Higher Low

Điều kiện SELL:
    (SH_last.high < SH_prev.high) AND   ← Lower High
    (SL_last.low  < SL_prev.low)        ← Lower Low

Còn lại: NEUTRAL
```

**Tại sao cần đủ 2 điều kiện (cả HH và HL, hoặc cả LH và LL)?**
- Chỉ dùng 1 điều kiện (ví dụ: chỉ HH) → dễ nhầm trong thị trường sideway khi có 1 spike bất thường.
- Yêu cầu cả 2 điều kiện → Higher confidence, ít false positive.

**Tham số cho AI tuning trong Phase 5:**
```python
FRACTAL_PERIOD       = 2    # Số nến mỗi bên để xác nhận Fractal (1–5)
MS_SWING_LOOKBACK    = 50   # Số nến H1 tối đa để tìm Swing (tránh swing quá cũ)
MS_MIN_SWINGS_REQUIRED = 2  # Số swing tối thiểu để confirm bias (không NEUTRAL bừa)
```

---

## 2. Thuật toán SMC FVG M15 — 3-Candle Imbalance + Mitigation

### 2.1 Định nghĩa Fair Value Gap (FVG)

**FVG (Fair Value Gap / Imbalance)** là vùng giá trống xuất hiện khi 3 nến liên tiếp tạo khoảng trống không có giao dịch:

```
BULLISH FVG (3 nến tăng mạnh):

Nến A       Nến B        Nến C
  ██           ██████        ██
  ██     ↑     ██████        ██
  ██   MOVE    ██████   ↑    ██
  ██           ██████   FVG  ██
               ██████        ██

Điều kiện: low_C > high_A  → FVG = [high_A, low_C]
(Khoảng trống giữa đỉnh nến A và đáy nến C)
```

```
BEARISH FVG (3 nến giảm mạnh):

Nến A       Nến B        Nến C
  ██           ██████        ██
  ██     ↓     ██████        ██
  ██   MOVE    ██████        ██
               ██████   ↓    ██
                         FVG  ██
                              ██

Điều kiện: high_C < low_A  → FVG = [high_C, low_A]
(Khoảng trống giữa đáy nến A và đỉnh nến C)
```

---

### 2.2 Điều kiện xác nhận FVG hợp lệ

Không phải mọi gap 3 nến đều là FVG giao dịch được. Cần thêm bộ lọc:

| Điều kiện | Công thức | Lý do |
|-----------|-----------|-------|
| **Gap tối thiểu** | `gap_size >= FVG_MIN_GAP_MULTIPLE × ATR` | Lọc noise, chỉ lấy FVG đủ lớn để giá quay lại |
| **Nến B là Impulse** | `body_B / (high_B - low_B) >= FVG_IMPULSE_BODY_RATIO` | Nến giữa phải có thân lớn (>= 60% chiều dài nến) → thực sự có lực đẩy mạnh |
| **Chỉ nến đã đóng** | `i <= len(df_m15) - 2` | Anti-Repainting — không dùng nến đang chạy |

**Tham số cho AI tuning:**
```python
FVG_MIN_GAP_MULTIPLE   = 0.3   # gap_size >= 0.3 × ATR14 (AI tune: 0.1–1.0)
FVG_IMPULSE_BODY_RATIO = 0.6   # body/range nến B >= 60% (AI tune: 0.4–0.8)
FVG_MAX_AGE_CANDLES    = 100   # FVG quá cũ (> 100 nến M15 = ~25 giờ) → bỏ qua
```

---

### 2.3 Cơ chế Lưu trữ FVG — Unmitigated List

**Mỗi FVG object chứa:**
```python
{
    "time"    : Timestamp,      # Thời điểm nến B đóng cửa (origin)
    "type"    : "BULLISH" | "BEARISH",
    "top"     : float,          # Cạnh trên của FVG
    "bottom"  : float,          # Cạnh dưới của FVG
    "mitigated": False          # Trạng thái (False = đang mở, True = đã lấp)
}
```

**Logic quét và lưu FVG mới:**
```
function scan_new_fvgs(df_m15_safe):
    new_fvgs = []
    for i in range(1, len(df_m15_safe) - 1):
        candle_A = df_m15_safe.iloc[i - 1]
        candle_B = df_m15_safe.iloc[i]
        candle_C = df_m15_safe.iloc[i + 1]

        # Kiểm tra Bullish FVG
        if candle_C['low'] > candle_A['high']:
            gap_size = candle_C['low'] - candle_A['high']
            if gap_size >= FVG_MIN_GAP_MULTIPLE × ATR:
                body_B = abs(candle_B['close'] - candle_B['open'])
                range_B = candle_B['high'] - candle_B['low']
                if body_B / range_B >= FVG_IMPULSE_BODY_RATIO:
                    new_fvgs.append({
                        "time"     : candle_B['time'],
                        "type"     : "BULLISH",
                        "top"      : candle_C['low'],
                        "bottom"   : candle_A['high'],
                        "mitigated": False
                    })

        # Kiểm tra Bearish FVG (đối xứng)
        if candle_C['high'] < candle_A['low']:
            ...  # Tương tự
    return new_fvgs
```

---

### 2.4 Cơ chế Mitigation (Xóa FVG đã bị lấp)

**FVG bị Mitigated khi:** giá quay lại chạm vào vùng FVG (50% hoặc full).

**Dự án này dùng chuẩn "50% Mitigation"** (SMC standard):
- **Bullish FVG:** Bị mitigated khi `close_price <= bottom + (top - bottom) × FVG_MITIGATION_LEVEL`
- **Bearish FVG:** Bị mitigated khi `close_price >= top - (top - bottom) × FVG_MITIGATION_LEVEL`

```python
FVG_MITIGATION_LEVEL = 0.5  # 50% (AI tune: 0.0 = touch, 0.5 = half, 1.0 = full fill)
```

**Logic cập nhật Mitigation mỗi chu kỳ:**
```
current_price = df_m15.iloc[-1]['close']  # Giá nến đang chạy (OK để check price)

for fvg in active_fvgs:
    midpoint = fvg['bottom'] + (fvg['top'] - fvg['bottom']) * FVG_MITIGATION_LEVEL

    if fvg['type'] == 'BULLISH':
        if current_price <= midpoint:
            fvg['mitigated'] = True   # Giá lấp 50% Bullish FVG từ trên xuống

    elif fvg['type'] == 'BEARISH':
        if current_price >= midpoint:
            fvg['mitigated'] = True   # Giá lấp 50% Bearish FVG từ dưới lên

# Lọc ra chỉ giữ FVG chưa bị lấp
active_fvgs = [f for f in active_fvgs if not f['mitigated']]
```

**Xử lý FVG quá cũ (Age Filter):**
```
current_index = len(df_m15_safe) - 1
active_fvgs = [
    f for f in active_fvgs
    if (current_index - df_m15_safe.index.get_loc(f['time'])) <= FVG_MAX_AGE_CANDLES
]
```

---

## 3. Đề xuất Cấu trúc Dữ liệu cho FVG List — Queue hay Deque?

### 3.1 So sánh các cấu trúc

| Cấu trúc | Thêm FVG mới | Xóa FVG cũ | Duyệt toàn bộ | RAM Usage | Phù hợp |
|----------|-------------|-----------|--------------|-----------|---------|
| `list` (hiện tại) | O(1) | O(n) với list comprehension | O(n) | Bình thường | ✅ OK cho n < 200 |
| `collections.deque` | O(1) ở đầu/cuối | O(1) ở đầu/cuối | O(n) | Nhỉnh hơn list 1 chút | ✅ **TỐT NHẤT** |
| `queue.Queue` | O(1) | O(1) | ❌ Không hỗ trợ iterate | Trung bình | ❌ Không phù hợp |
| `dict` keyed by time | O(1) | O(1) | O(n) | Cao hơn | ✅ Nếu cần lookup by time |

### 3.2 Khuyến nghị: `collections.deque(maxlen=FVG_MAX_POOL_SIZE)`

**Lý do chọn `deque`:**

1. **Tự động giới hạn RAM:** `deque(maxlen=50)` tự động xóa FVG cũ nhất khi thêm FVG mới vượt quá 50 → không bao giờ bị memory leak.
2. **O(1) thêm/xóa hai đầu:** Phù hợp pattern "thêm FVG mới vào cuối, xóa FVG cũ ở đầu" — nhanh hơn `list.pop(0)` là O(n).
3. **Vẫn iterable:** Có thể dùng `for fvg in active_fvgs` bình thường.
4. **Thread-safe hơn list:** Quan trọng khi Phase 4+ có thể chạy multithread.

**Cách triển khai:**
```python
from collections import deque

FVG_MAX_POOL_SIZE = 50  # Tham số — AI có thể tuning

active_fvgs: deque = deque(maxlen=FVG_MAX_POOL_SIZE)

# Thêm FVG mới
active_fvgs.append(new_fvg_dict)

# Duyệt và lọc (tạo deque mới từ filter)
active_fvgs = deque(
    (f for f in active_fvgs if not f['mitigated']),
    maxlen=FVG_MAX_POOL_SIZE
)
```

**Ngoài ra, dùng `dict` keyed by timestamp** nếu Phase sau cần lookup FVG theo thời gian O(1) (ví dụ AI truy vấn "FVG tạo lúc 14:00 có còn active không?"):
```python
active_fvgs_dict: dict[pd.Timestamp, dict] = {}
```
→ Quyết định cuối sẽ tùy thuộc vào cách Phase 5 ML model query FVG.

---

## 4. Kế hoạch Tham số hóa — AI Tunable Parameters

Toàn bộ hằng số được tập trung vào 1 block duy nhất (hoặc `config/settings.py`) để Phase 5 AI có thể tự động tuning:

```python
# ============================================================
# STRATEGY ENGINE — AI TUNABLE PARAMETERS
# Phase 5 ML Optimizer sẽ tự động chỉnh các biến này
# ============================================================

# --- VŨ KHÍ 1: MARKET STRUCTURE (H1) ---
FRACTAL_PERIOD          = 2    # Số nến mỗi bên để xác nhận Fractal [1–5]
MS_SWING_LOOKBACK       = 50   # Số nến H1 để tìm Swing trong quá khứ [20–100]
MS_MIN_SWINGS_REQUIRED  = 2    # Số cặp swing tối thiểu để confirm bias [1–3]

# --- VŨ KHÍ 2: SMC FVG (M15) ---
FVG_MIN_GAP_MULTIPLE    = 0.3  # Gap tối thiểu = x × ATR14 [0.1–1.0]
FVG_IMPULSE_BODY_RATIO  = 0.6  # Tỷ lệ thân/chiều dài nến giữa [0.4–0.8]
FVG_MITIGATION_LEVEL    = 0.5  # % FVG cần lấp để bị Mitigated [0.0–1.0]
FVG_MAX_AGE_CANDLES     = 100  # Tuổi thọ tối đa của FVG (số nến M15) [50–200]
FVG_MAX_POOL_SIZE       = 50   # Số FVG active tối đa trong bộ nhớ [20–100]
```

---

## 5. Rủi ro & Biện pháp Giảm thiểu

| Rủi ro | Mô tả | Biện pháp |
|--------|-------|-----------|
| **Edge case: DataFrame quá ngắn** | `df_h1` < `2 × FRACTAL_PERIOD + 1` nến → index lỗi | Guard: `if len(df_safe) < 2 * FRACTAL_PERIOD + 1: return 'NEUTRAL'` |
| **FVG trùng lặp** | Quét lại toàn bộ lịch sử mỗi chu kỳ → thêm FVG đã có | Dùng `time` của nến B làm khóa kiểm tra trùng trước khi append |
| **ATR = 0 hoặc None** | Dữ liệu thiếu → `FVG_MIN_GAP_MULTIPLE × ATR` = 0 → tất cả gap đều pass | Guard: `if atr is None or atr == 0: skip FVG size filter` |
| **Bias mâu thuẫn** | H1 BUY nhưng M15 chỉ có Bearish FVG | Hàm trả về kết quả riêng biệt, logic tổng hợp ở `main.py` — **không** gộp trong Engine |
| **Thay đổi FRACTAL_PERIOD mid-session** | AI đột ngột đổi từ 2 → 3 → lịch sử Swing bị vô hiệu | Khi AI cập nhật params → gọi lại `identify_market_structure` toàn bộ, không dùng cache |

---

## Báo cáo Tóm tắt (Theo AI_SOP_TEMPLATE Format)

**Task 3.1: Phân tích Logic H1 & M15**

* **Nội dung thay đổi, hoạt động:**
  - `docs/walkthrough.md` — Bổ sung toàn bộ phần "Phase 3 — Task 3.1" gồm 5 mục: (1) thuật toán Fractal Anti-Repainting H1, (2) thuật toán SMC FVG 3-nến + mitigation M15, (3) so sánh cấu trúc dữ liệu deque vs list, (4) bảng AI tunable parameters, (5) bảng rủi ro và biện pháp.
  - `History.txt` — Ghi log Phase 3 Task 3.1 vào file.
  - Git: Tạo và checkout nhánh `feature/phase3.1-h1-m15-logic`.
  - **Chưa viết bất kỳ dòng code nào** — đang chờ "PROCEED" từ TechLead.

* **Lý do chọn Fractal Period = 2 (2 nến mỗi bên):**
  - Fractal Period = 1 (1 nến mỗi bên): Quá nhạy → nhận diện quá nhiều Swing giả (false swing) trong thị trường nhiễu.
  - Fractal Period = 2 (2 nến mỗi bên): **Cân bằng tối ưu** cho H1 — đủ "nặng" để lọc noise, nhưng không bỏ lỡ các swing thực sự quan trọng.
  - Fractal Period = 3+: Quá cứng nhắc → bỏ lỡ Swing cấp thấp, kém nhạy với BOS/CHoCH cục bộ.
  - XAGUSD có thanh khoản thấp hơn XAUUSD → Fractal 2 phù hợp hơn Fractal 1 để tránh spike noise.

* **Đề xuất cải tiến — `deque` thay `list` cho FVG Pool:**
  - `collections.deque(maxlen=FVG_MAX_POOL_SIZE)` ưu việt hơn `list` ở 3 điểm: (1) Tự động giới hạn RAM qua `maxlen` — không bao giờ memory leak dù bot chạy nhiều ngày; (2) O(1) thêm/xóa ở đầu và cuối — tối ưu hơn `list.pop(0)` là O(n); (3) Thread-safer hơn khi Phase 4+ có thể giới thiệu multithreading. Khi Phase 5 ML cần lookup FVG theo timestamp O(1), chuyển sang `dict[Timestamp, FVGDict]` là bước nâng cấp tự nhiên.

---

## ✅ Task 3.1 — Implementation Report (POST-PROCEED)

**Status:** 🟢 COMPLETED | **Commit:** `8e9eaed` | **Branch:** `feature/phase3.1-h1-m15-logic`

### Files đã tạo / thay đổi

| File | Thay đổi | Dòng |
|------|----------|------|
| `core/strategy_engine.py` | [NEW] Class StrategyEngine — 2 vũ khí H1+M15 | ~370 |
| `config/settings.py` | [MODIFY] Thêm 8 AI-tunable params | +20 |
| `main.py` | [MODIFY] Phase 3 smoke test — H1 Bias + FVG list | +100 |
| `History.txt` | [MODIFY] Log Phase 3 Task 3.1 | +10 |
| `docs/walkthrough.md` | [MODIFY] SOP analysis + completion report | +400 |

### Nội dung chi tiết `core/strategy_engine.py`

```
StrategyEngine
├── create_fvg_pool()                  → deque(maxlen=50)  [static]
├── identify_market_structure(df_h1)   → 'BUY' | 'SELL' | 'NEUTRAL'
│   ├── df_safe = df_h1.iloc[:-1]     ← Anti-Repainting
│   ├── _is_swing_high(df, i, period)
│   ├── _is_swing_low(df, i, period)
│   └── HH+HL → BUY | LH+LL → SELL | else → NEUTRAL
├── find_active_fvgs(df_m15, fvg_pool) → list[FVGDict]
│   ├── df_safe = df_m15.iloc[:-1]    ← Anti-Repainting
│   ├── _calculate_atr(df, period)    → ATR14 (Wilder RMA)
│   ├── Quét 3-nến Bullish/Bearish FVG
│   ├── _is_valid_fvg() → gap>=0.3×ATR AND body_B/range_B>=60%
│   ├── Mitigation: price crosses 50% FVG midpoint
│   └── Age filter: FVG > 100 nến M15 → expired
└── Private helpers: _is_swing_high, _is_swing_low, _is_valid_fvg, _calculate_atr
```

### Output mẫu khi chạy `python main.py`

```
======================================================================
🧭 PHASE 3 — STRATEGY ENGINE SMOKE TEST
======================================================================

   ✅ H1:  200 nến  |  M15: 200 nến

----------------------------------------------------------------------
⚔️  VŨ KHÍ 1: Market Structure (H1)
----------------------------------------------------------------------

   🔴 H1 Directional Bias  :  SELL
   📌 Ý nghĩa: Xu hướng GIẢM — Chỉ tìm setup SHORT khi giá vào FVG cung

----------------------------------------------------------------------
⚔️  VŨ KHÍ 2: SMC FVG (M15)
----------------------------------------------------------------------

   📋 Tổng số FVG đang MỞ (Unmitigated): 4

     #  Type       Bottom       Top     Size  Thời gian tạo
   ----------------------------------------------------------------
     1  🔴 BEARISH    32.105    32.380   0.2750  2026-03-05 07:15:00
     2  🟢 BULLISH    31.820    31.950   0.1300  2026-03-05 05:00:00
     3  🔴 BEARISH    32.445    32.680   0.2350  2026-03-04 22:30:00
     4  🔴 BEARISH    32.920    33.105   0.1850  2026-03-04 19:45:00

   📊 Phân tích Alignment (H1 Bias ↔ FVG M15):
   ✅ ALIGNED — H1 SELL + 3 Bearish FVG → CÓ THỂ TÌM SHORT setup!

======================================================================
✅ PHASE 3 STRATEGY ENGINE — SMOKE TEST HOÀN TẤT
======================================================================
```
*(Giá trị minh họa — kết quả thực phụ thuộc vào thị trường XAGUSD thực)*

---

*Tài liệu này ghi lại toàn bộ quá trình phân tích → thiết kế → implementation của Task 3.1.*
*Antigravity sẵn sàng cho Task 3.2 — Vũ khí 3: Pinbar M5.*


---
---

# Phase 3 — Task 3.2: Phân tích Trigger M5 & VSA (ANALYZE & REPORT FIRST)

**Branch:** `feature/phase3.2-m5-vsa-trigger`
**Author:** Antigravity (AI Coder)
**Date:** 2026-03-05
**Status:** 🟡 PENDING TechLead Review — Awaiting "PROCEED" command

---

## Mục Lục

1. [Thuật toán nhận diện Pinbar/Hammer M5 — Toán học chính xác](#1-thuật-toán-nhận-diện-pinbarhammer-m5--toán-học-chính-xác)
2. [Thuật toán VSA — Relative Volume & Ngưỡng đột biến](#2-thuật-toán-vsa--relative-volume--ngưỡng-đột-biến)
3. [Logic phối hợp POI — Kiểm tra FVG M15 trước khi phát tín hiệu](#3-logic-phối-hợp-poi--kiểm-tra-fvg-m15-trước-khi-phát-tín-hiệu)
4. [Luồng xử lý tổng thể `check_m5_trigger()`](#4-luồng-xử-lý-tổng-thể-check_m5_trigger)
5. [Rủi ro & Biện pháp Giảm thiểu](#5-rủi-ro--biện-pháp-giảm-thiểu)

---

## 1. Thuật toán nhận diện Pinbar/Hammer M5 — Toán học chính xác

### 1.1 Bài toán: Pinbar hợp lệ vs Pinbar nhiễu

**Pinbar** (Price Action Bar / Pin Bar) là nến có râu dài và thân nhỏ, dấu hiệu giá **từ chối vùng giá** mạnh — smart money đẩy giá đi rồi phục hồi về. Tuy nhiên trong thực tế, có rất nhiều "Pinbar rởm":

| Loại nến | Mô tả | Hành động |
|----------|-------|-----------|
| **Pinbar thật** | Râu dài đột ngột, thân nhỏ, xảy ra tại vùng hỗ trợ/kháng cự | ✅ Giao dịch |
| **Spike spread** | XAGUSD giãn spread lúc tin tức → nến có râu dài nhưng không phải price action thật | ❌ Lọc bằng ATR |
| **Doji nhiễu** | Thân siêu nhỏ, hai râu đều dài → thị trường do dự, không phải từ chối giá | ❌ Lọc bằng hướng râu |
| **Nến bình thường** | Râu ngắn, thân lớn → đây là Impulse, không phải Pinbar | ❌ Lọc bằng wick ratio |

### 1.2 Phân tích toán học cấu trúc nến Pinbar

Mỗi nến có 4 thành phần:
```
ANATOMY OF A CANDLE:
                  ─── HIGH
                   |
               [UPPER WICK]
                   |
             ┌─────────┐  ─── max(open, close)
             │  BODY   │
             └─────────┘  ─── min(open, close)
                   |
               [LOWER WICK]
                   |
                  ─── LOW

Candle RANGE     = HIGH - LOW
Upper Wick (UW)  = HIGH - max(OPEN, CLOSE)
Lower Wick (LW)  = min(OPEN, CLOSE) - LOW
Body (B)         = |CLOSE - OPEN|
```

### 1.3 Công thức toán học nhận diện Pinbar chính xác

**Định nghĩa chuẩn — 3-Ratio System:**

```
Đặt:
    RANGE   = high - low          (tổng chiều dài nến)
    UW      = high - max(open, close)   (upper wick)
    LW      = min(open, close) - low    (lower wick)
    BODY    = |close - open|            (thân nến)
    POINT   = mt5.symbol_info('XAGUSD').point  ≈ 0.001

Điều kiện RANGE hợp lệ (tránh DIV/0):
    RANGE > POINT  →  nến không phải doji hoàn toàn

=== HAMMER (Bullish Pinbar — tín hiệu BUY) ===
Điều kiện:
  (1) Lower Wick là "râu từ chối" chính:
      LW / RANGE >= PINBAR_WICK_RATIO   [khoảng 0.60]
      → Râu dưới >= 60% tổng chiều dài nến

  (2) Upper Wick nhỏ (không phải shooting star lẫn lộn):
      UW / RANGE <= PINBAR_BODY_MAX_RATIO   [khoảng 0.25]
      → Râu trên <= 25% tổng chiều dài nến

  (3) Thân nến nhỏ (đặc trưng từ chối giá):
      BODY / RANGE <= PINBAR_BODY_MAX_RATIO   [khoảng 0.30]
      → Thân <= 30% tổng chiều dài nến — thể hiện lực đẩy ngược mạnh

=== SHOOTING STAR (Bearish Pinbar — tín hiệu SELL) ===
Điều kiện (đối xứng):
  (1) UW / RANGE >= PINBAR_WICK_RATIO   [>= 0.60]
  (2) LW / RANGE <= PINBAR_BODY_MAX_RATIO   [<= 0.25]
  (3) BODY / RANGE <= PINBAR_BODY_MAX_RATIO   [<= 0.30]
```

**Ví dụ số học minh họa:**
```
Nến M5 XAGUSD:
  open=30.500, high=30.620, low=30.350, close=30.530

  RANGE  = 30.620 - 30.350 = 0.270
  UW     = 30.620 - max(30.500, 30.530) = 30.620 - 30.530 = 0.090
  LW     = min(30.500, 30.530) - 30.350 = 30.500 - 30.350 = 0.150
  BODY   = |30.530 - 30.500| = 0.030

  Kiểm tra Hammer:
  LW/RANGE  = 0.150 / 0.270 = 55.6%  → < 60% ❌ (không đủ)

Nến M5 thứ 2:
  open=30.500, high=30.560, low=30.300, close=30.510

  RANGE  = 0.260
  UW     = 30.560 - 30.510 = 0.050
  LW     = 30.500 - 30.300 = 0.200
  BODY   = 0.010

  Kiểm tra Hammer:
  LW/RANGE  = 0.200 / 0.260 = 76.9%  ✅  >= 60%
  UW/RANGE  = 0.050 / 0.260 = 19.2%  ✅  <= 25%
  BODY/RANGE= 0.010 / 0.260 = 3.8%   ✅  <= 30%
  → VALID HAMMER ✅
```

### 1.4 Tham số AI-Tunable cho Pinbar

```python
# config/settings.py — VŨ KHÍ 3
PINBAR_WICK_RATIO      = 0.60  # Râu chính / tổng nến >= 60%   [range: 0.50–0.75]
PINBAR_BODY_MAX_RATIO  = 0.30  # Thân + râu phụ <= 30%          [range: 0.20–0.40]
ATR_PINBAR_MIN_MULT    = 0.5   # Nến quá nhỏ < 0.5×ATR → loại bỏ [range: 0.3–1.0]
```

---

## 2. Thuật toán VSA — Relative Volume & Ngưỡng đột biến

### 2.1 Tổng quan VSA (Volume Spread Analysis)

**VSA** phân tích mối quan hệ giữa **Volume (dòng tiền)** và **Price Spread (biên độ giá)** để xác định "Smart Money" có đang tham gia hay không.

**Nguyên tắc cốt lõi VSA áp dụng trong Rabit_FTMO:**
> Một nến Pinbar **có ý nghĩa** khi đi kèm Volume đột biến — tức là Smart Money thực sự đang đẩy giá, không phải biến động ngẫu nhiên hay spread giãn.

| Volume tại Pinbar | Ý nghĩa | Hành động |
|--------------------|---------|-----------|
| **Volume đột biến (Spike)** | Smart Money tham gia mạnh — dấu hiệu đảo chiều thật | ✅ Phát tín hiệu |
| **Volume trung bình** | Không có xác nhận dòng tiền → từ chối giá chưa chắc chắn | ⚠️ Cân nhắc (optional filter) |
| **Volume thấp (dry-up)** | Thị trường thiếu người mua/bán → Pinbar là nhiễu | ❌ Loại bỏ |

### 2.2 Tại sao chọn SMA(20) thay vì các con số khác?

**So sánh các baseline alternatives:**

| Baseline | Công thức | Ưu điểm | Nhược điểm |
|----------|-----------|---------|------------|
| **SMA(10)** | TB 10 nến M5 (~50 phút) | Nhạy với volume gần nhất | Quá ngắn → bị distort bởi 1-2 spike vừa xảy ra |
| **SMA(20)** ✅ | TB 20 nến M5 (~100 phút) | **Cân bằng — đủ "nhớ" 1-2 phiên** | Mặc định công nghiệp (Bollinger Band cũng dùng SMA20) |
| **SMA(50)** | TB 50 nến M5 (~250 phút) | Ổn định hơn, ít bị outlier ảnh hưởng | Quá chậm → baseline "nhớ" thời điểm tin tức cũ |
| **EMA(20)** | EMA trọng số | Nhạy với volume mới | Phức tạp hơn, ít trực quan với trader |
| **Median(20)** | Trung vị 20 nến | Không bị ảnh hưởng bởi outlier | Khó interpret cho TechLead khi review log |

**Lý do chọn SMA(20):**
1. **Standard industry practice:** Bollinger Bands (20 period SMA), VWAP deviation analysis đều dùng window 20.
2. **~100 phút lookback:** Đủ để bao phủ "bối cảnh volume bình thường" của phiên giao dịch hiện tại mà không kéo dài vào phiên trước.
3. **Đơn giản, dễ audit:** `volume.rolling(20).mean()` — bất kỳ TechLead nào cũng có thể verify bằng tay.
4. **Phù hợp XAGUSD:** Silver có thanh khoản thấp hơn Gold — window 20 (~100 phút) phù hợp hơn window ngắn (10) để tránh false spike từ 1-2 tick volume bất thường.

### 2.3 Công thức tính VSA Relative Volume

```
=== CÀI ĐẶT BASELINE ===
vol_ma = SMA(tick_volume, VOLUME_MA_PERIOD)   # SMA20 của tick_volume
        = sum(tick_volume[-20:]) / 20          # Trung bình 20 nến M5 gần nhất

=== XÁC ĐỊNH NGƯỠNG ĐỘT BIẾN ===
Mức Volume đột biến (Spike):
    current_volume >= vol_ma × VSA_VOLUME_MULTIPLIER

Với:
    VSA_VOLUME_MULTIPLIER = 1.5   (AI-tunable, range: 1.2–2.5)
    → Volume nến hiện tại >= 1.5 lần trung bình 20 nến = Spike xác nhận

=== PHÂN LOẠI VOLUME (3 tiers) ===
    volume_ratio = current_volume / vol_ma

    ratio >= VSA_VOLUME_MULTIPLIER (>=1.5):  "SPIKE"   → ✅ Xác nhận VSA
    ratio >= 1.0:                             "NORMAL"  → ⚠️ Không xác nhận
    ratio <  1.0:                             "DRY-UP"  → ❌ Loại bỏ
```

**Ví dụ số học:**
```
tick_volume 20 nến M5 gần nhất:
    [120, 85, 200, 95, 110, 175, 80, 130, 90, 145,
     160, 70, 115, 195, 88, 102, 135, 78, 165, 92]

vol_ma_20 = sum / 20 = 2430 / 20 = 121.5

Nến Pinbar hiện tại:
    current_volume = 215

volume_ratio = 215 / 121.5 = 1.77

1.77 >= 1.5  → SPIKE ✅ — VSA xác nhận
```

### 2.4 Tham số AI-Tunable cho VSA

```python
# config/settings.py — VŨ KHÍ 3 (tiếp)
VOLUME_MA_PERIOD      = 20    # Đã có sẵn — tính SMA baseline  [range: 10–50]
VSA_VOLUME_MULTIPLIER = 1.5   # Ngưỡng Spike = x × SMA20       [range: 1.2–2.5]
```

---

## 3. Logic phối hợp POI — Kiểm tra FVG M15 trước khi phát tín hiệu

### 3.1 Tại sao cần kiểm tra FVG M15 trước?

**Nguyên tắc SMC (Smart Money Concepts):**
> Tín hiệu đảo chiều chỉ có giá trị cao khi xảy ra **TẠI** vùng thanh khoản (POI — Point of Interest).
> Một Pinbar tại vùng random không có POI = Low Probability Setup.
> Một Pinbar TẠI FVG M15 = High Probability Setup (Smart Money đã tạo ra imbalance đó).

```
❌ Pinbar KHÔNG tại FVG:
    ...random price action...
    [Pinbar xảy ra]  ← Không biết smart money có quan tâm không
    → Win rate thấp

✅ Pinbar TẠI FVG M15:
    FVG được tạo trước (imbalance zone)
    [Giá quay lại FVG]
    [Pinbar xảy ra TẠI FVG bottom/top]  ← Smart money đã "đặt bẫy" tại đây
    → Win rate cao hơn đáng kể
```

### 3.2 Thuật toán kiểm tra "nến M5 nằm trong FVG M15"

**Điều kiện giao nhau (Intersection Test):**

```
FVG được định nghĩa bởi:
    fvg["top"]    = Cạnh trên FVG (price level)
    fvg["bottom"] = Cạnh dưới FVG (price level)
    fvg["type"]   = "BULLISH" | "BEARISH"

Nến M5 hiện tại (nến cuối đã đóng):
    candle_high  = df_m5.iloc[-2]["high"]    ← Anti-Repainting: nến đã đóng
    candle_low   = df_m5.iloc[-2]["low"]
    candle_close = df_m5.iloc[-2]["close"]

=== ĐIỀU KIỆN GIAO NHAU (Overlap) ===
Nến M5 được coi là "nằm trong FVG" nếu:

    overlap = (candle_low <= fvg["top"]) AND (candle_high >= fvg["bottom"])

Logic này phát hiện mọi trường hợp nến M5 chạm vào FVG:
    - Nến M5 hoàn toàn nằm trong FVG
    - Nến M5 đâm vào FVG từ trên xuống
    - Nến M5 đâm vào FVG từ dưới lên
    - Nến M5 bao phủ toàn bộ FVG (nhịp di chuyển mạnh)
```

**Điều kiện hướng (Alignment):**

```
=== ALIGNMENT FILTER — Logic tổng hợp 3 tầng ===

Tín hiệu BUY chỉ được phát khi:
  (A) H1 Bias = "BUY"                              ← Tầng 1: The Compass
  (B) FVG M15 type = "BULLISH" (unmitigated)       ← Tầng 2: POI âm tính với bias
  (C) Hammer Pinbar được xác nhận tại FVG này      ← Tầng 3: The Trigger
  (D) VSA Volume Spike được xác nhận               ← Tầng 3+: Bộ lọc VSA

Tín hiệu SELL chỉ được phát khi:
  (A) H1 Bias = "SELL"                             ← Tầng 1
  (B) FVG M15 type = "BEARISH" (unmitigated)       ← Tầng 2
  (C) Shooting Star Pinbar xác nhận tại FVG        ← Tầng 3
  (D) VSA Volume Spike xác nhận                    ← Tầng 3+
```

### 3.3 Pseudocode hoàn chỉnh cho logic POI

```python
def _is_candle_in_fvg(candle_high, candle_low, fvg) -> bool:
    """Kiểm tra nến M5 có giao nhau với FVG M15 không."""
    return (candle_low <= fvg["top"]) and (candle_high >= fvg["bottom"])


def _find_matching_fvg(candle_high, candle_low, candle_type, active_fvgs):
    """
    Tìm FVG M15 phù hợp với nến Pinbar M5.
    
    candle_type: "HAMMER" (cần BULLISH FVG) | "SHOOTING_STAR" (cần BEARISH FVG)
    """
    required_fvg_type = "BULLISH" if candle_type == "HAMMER" else "BEARISH"
    
    matching_fvgs = [
        fvg for fvg in active_fvgs
        if fvg["type"] == required_fvg_type
        and _is_candle_in_fvg(candle_high, candle_low, fvg)
    ]
    
    # Nếu có nhiều FVG match → ưu tiên FVG mới nhất (gần đây nhất)
    if matching_fvgs:
        return matching_fvgs[-1]   # deque được append theo thứ tự thời gian
    return None
```

---

## 4. Luồng xử lý tổng thể `check_m5_trigger()`

### 4.1 Flowchart logic

```
check_m5_trigger(df_m5, active_fvgs, h1_bias)
│
├── [Guard 1] df_m5 đủ dài? (>= VOLUME_MA_PERIOD + 1 nến)
│   └── Không → return NONE + log "Data M5 không đủ"
│
├── [Guard 2] h1_bias != NEUTRAL?
│   └── Không → return NONE + log "H1 Bias = NEUTRAL, bỏ qua trigger"
│
├── [Guard 3] active_fvgs không rỗng?
│   └── Không → return NONE + log "Không có FVG M15 active"
│
├── [Bước 1] Lấy nến M5 đã đóng gần nhất (Anti-Repainting)
│   └── candle = df_m5.iloc[-2]   ← Nến đã đóng ("candle[-2]" = nến cuối ĐÓNG)
│
├── [Bước 2] Kiểm tra ATR Minimum Size
│   └── nến_range < ATR_PINBAR_MIN_MULT × atr → return NONE + log "Nến quá nhỏ (spread noise)"
│
├── [Bước 3] Kiểm tra Pinbar Pattern
│   ├── is_hammer()       → candle_type = "HAMMER"
│   ├── is_shooting_star() → candle_type = "SHOOTING_STAR"
│   └── Không phải Pinbar → return NONE + log "Không phải Pinbar pattern"
│
├── [Bước 4] Kiểm tra Alignment (Bias vs Pinbar type)
│   ├── h1_bias="BUY" nhưng candle_type="SHOOTING_STAR" → return NONE + log "Counter-trend"
│   └── h1_bias="SELL" nhưng candle_type="HAMMER" → return NONE + log "Counter-trend"
│
├── [Bước 5] Kiểm tra POI (FVG M15)
│   └── matching_fvg = _find_matching_fvg(...) 
│       └── None → return NONE + log "Pinbar nằm ngoài POI (FVG M15)"
│
├── [Bước 6] Kiểm tra VSA Volume
│   ├── Tính vol_ma = SMA(tick_volume, VOLUME_MA_PERIOD)
│   └── current_volume < vol_ma × VSA_VOLUME_MULTIPLIER
│       └── return NONE + log "Volume thấp — Pinbar không xác nhận VSA"
│
└── [Output] Tất cả điều kiện pass:
    ├── candle_type = "HAMMER"        → return "SIGNAL_BUY"
    └── candle_type = "SHOOTING_STAR" → return "SIGNAL_SELL"
    + log đầy đủ: fvg_matched, vol_ratio, candle_ratios
```

### 4.2 Constants cần thêm vào `config/settings.py`

```python
# ============================================================
# VŨ KHÍ 3: M5 TRIGGER (Pinbar + VSA) — AI TUNABLE PARAMETERS
# ============================================================
PINBAR_WICK_RATIO      = 0.60   # Râu chính / tổng nến >= 60%        [range: 0.50–0.75]
PINBAR_BODY_MAX_RATIO  = 0.30   # Thân + râu phụ mỗi cái <= 30%      [range: 0.20–0.40]
ATR_PINBAR_MIN_MULT    = 0.50   # Nến quá nhỏ < 0.5×ATR14 → loại     [range: 0.30–1.00]
VSA_VOLUME_MULTIPLIER  = 1.50   # Volume Spike = x × SMA20 volume     [range: 1.20–2.50]
```

---

## 5. Rủi ro & Biện pháp Giảm thiểu

| Rủi ro | Mô tả | Biện pháp |
|--------|-------|-----------|
| **Spike râu do spread giãn** | XAGUSD phút tin tức có spread 5–10x bình thường → tạo Pinbar "rởm" | Bộ lọc `ATR_PINBAR_MIN_MULT`: nến < 0.5×ATR → loại; bộ lọc VSA: volume thật phải đột biến |
| **Doji bị nhầm Pinbar** | Body = 0, hai râu đều nhau → pass điều kiện LW/RANGE | Điều kiện `UW/RANGE <= PINBAR_BODY_MAX_RATIO`: đảm bảo râu phụ nhỏ, phân biệt Doji vs Pinbar |
| **Volume M5 không chuẩn** | MT5 tick_volume ≠ real traded volume (chỉ là số lượng tick) | Dùng tick_volume là consistent cross-broker — relative comparison (ratio) đáng tin cậy hơn absolute value |
| **FVG M15 không có trong cửa sổ M5** | FVG tạo quá lâu → df_m5 window (100 nến) không bao phủ | `FVG_MAX_AGE_CANDLES` đã lọc FVG cũ từ Vũ khí 2; không ảnh hưởng logic tìm kiếm M5 |
| **Multiple matching FVGs** | Nến M5 nằm trong 2 FVG M15 cùng lúc | Ưu tiên FVG mới nhất (append vào deque theo thứ tự) — FVG mới = POI "tươi" hơn |
| **NONE signal liên tục** | Bot không ra tín hiệu vì quá nhiều bộ lọc | Logger ghi rõ **lý do cụ thể** từng lần từ chối → TechLead có thể review và relax parameters |

---

## Báo cáo Tóm tắt (Theo AI_SOP_TEMPLATE Format)

**Task 3.2: Phân tích Trigger M5 & VSA**

* **Nội dung thay đổi, hoạt động:**
  - `docs/walkthrough.md` — Bổ sung toàn bộ phần "Phase 3 — Task 3.2" gồm 5 mục phân tích: (1) Công thức toán học 3-ratio nhận diện Pinbar/Hammer vs Shooting Star, phân biệt nến thật vs nhiễu spread; (2) Thuật toán VSA Relative Volume với baseline SMA(20), phân loại 3 tiers (Spike/Normal/Dry-up) và ngưỡng 1.5× trung bình; (3) Logic giao nhau FVG M15 (overlap test + alignment filter 3 tầng H1-M15-M5); (4) Flowchart đầy đủ `check_m5_trigger()` với 6 bước lọc tuần tự và logger lý do từ chối; (5) Bảng rủi ro và biện pháp.
  - `History.txt` — Ghi log Phase 3 Task 3.2.
  - Git: Tạo và checkout nhánh `feature/phase3.2-m5-vsa-trigger` (sau khi merge Task 3.1 → main).
  - **Chưa viết bất kỳ dòng code nào** — đang chờ "PROCEED" từ TechLead.

* **Lý do chọn SMA(20) cho Volume baseline:**
  - **Cân bằng lookback:** 20 nến M5 = ~100 phút — đủ "nhớ" bối cảnh volume 1-2 tiếng gần nhất mà không kéo sang phiên cũ. SMA(10) quá ngắn → dễ bị distort bởi 1 spike vừa xảy ra. SMA(50) quá dài → nhớ cả phiên trước, baseline không đại diện phiên hiện tại.
  - **Industrial standard:** SMA(20) là window mặc định của Bollinger Bands, VWAP deviation — cộng đồng trading tính là "base market tempo" trong ~2 tiếng.
  - **XAGUSD đặc thù:** Bạc thanh khoản thấp hơn Gold, volume fluctuation cao hơn → cần window đủ rộng để tránh false spike từ 1-2 tick bất thường.
  - **Dễ audit:** `volume.rolling(20).mean()` rõ ràng, TechLead verify được bằng tính tay dễ dàng.

* **Đề xuất cải tiến — Bộ lọc ATR tối thiểu cho Pinbar:**
  - **CÓ — Đây là bộ lọc BẮT BUỘC với XAGUSD.** `ATR_PINBAR_MIN_MULT = 0.5` nghĩa là: nếu tổng chiều dài nến (RANGE) < 0.5×ATR14, nến bị loại ngay tại Bước 2 — trước cả khi tính Pinbar ratio. Lý do: Spread XAGUSD có thể giãn 5–10× lúc NFP hoặc FOMC. Nếu spread = 0.050 nhưng ATR14 = 0.250 → RANGE = 0.060 (chủ yếu là spread) → nến có râu 60% nhưng đó là spread, không phải price action. Bộ lọc ATR loại bỏ những "Pinbar ma" này hiệu quả.
  - **Cải tiến nâng cao (Phase 5+):** Thêm kiểm tra `NEWS_BLOCK_MINUTES` — nếu Pinbar xảy ra trong vòng ±30 phút tin tức Đỏ → tự động skip (spread spike/news candle). Logic này kết hợp với News Filter trong `settings.py` (`NEWS_BLOCK_MINUTES = 30`).

---

*Tài liệu này được viết phục vụ TechLead Review trước khi bắt đầu viết code Task 3.2.*
*Xem xét và gõ "PROCEED" để AI bắt đầu implementation `check_m5_trigger()`.*


---

## ✅ Task 3.2 — Implementation Report (POST-PROCEED)

**Status:** 🟢 COMPLETED | **Branch:** `feature/phase3.2-m5-vsa-trigger`

### 1. Files đã tạo / thay đổi

| File | Thay đổi | Nội dung chính |
|------|----------|----------------|
| `core/strategy_engine.py` | [MODIFY] | Thêm hàm `check_m5_trigger()` và 2 private helpers (`_is_candle_in_fvg`, `_find_matching_fvg`). Tích hợp 6 bước lọc thuật toán Pinbar + VSA. |
| `config/settings.py` | [MODIFY] | Phơi bày 4 tham số AI-tunable: `PINBAR_WICK_RATIO`, `PINBAR_BODY_MAX_RATIO`, `ATR_PINBAR_MIN_MULT`, `VSA_VOLUME_MULTIPLIER`. |
| `main.py` | [MODIFY] | Cập nhật Smoke Test: kéo dữ liệu M5, in kết quả M5 Trigger (kèm emoji xanh/đỏ). |
| `docs/walkthrough.md` | [MODIFY] | Phân tích thuật toán và báo cáo POST-PROCEED này. |
| `History.txt` | [MODIFY] | Ghi log hoàn thành Task 3.2. |

### 2. Output mẫu khi chạy `python main.py`

```text
======================================================================
🧭 PHASE 3 — STRATEGY ENGINE SMOKE TEST
======================================================================

   ✅ H1:  200 nến  |  M15: 200 nến

----------------------------------------------------------------------
⚔️  VŨ KHÍ 1: Market Structure (H1)
----------------------------------------------------------------------

   🔴 H1 Directional Bias  :  SELL
   📌 Ý nghĩa: Xu hướng GIẢM — Chỉ tìm setup SHORT khi giá vào FVG cung

----------------------------------------------------------------------
⚔️  VŨ KHÍ 2: SMC FVG (M15)
----------------------------------------------------------------------

   📋 Tổng số FVG đang MỞ (Unmitigated): 7
   ...
   📊 Phân tích Alignment (H1 Bias ↔ FVG M15):
   ✅ ALIGNED — H1 SELL + 3 Bearish FVG → CÓ THỂ TÌM SHORT setup!

----------------------------------------------------------------------
⚔️  VŨ KHÍ 3: M5 Trigger (Pinbar & VSA)
----------------------------------------------------------------------
2026-03-05 11:16:14 | INFO     | rabit.system | main | 📥 Kéo 100 nến M5 XAGUSD...

   ✅ M5:  100 nến
      → M5 Signal: ⚪ NONE (Không có tín hiệu Pinbar hợp lệ hoặc không có xác nhận VSA)

======================================================================
✅ PHASE 3 STRATEGY ENGINE — SMOKE TEST HOÀN TẤT
======================================================================
```
*(Hiện tại M5 không có tín hiệu, bot thông báo ⚪ NONE đúng như logic. Log hệ thống ghi nhận đầy đủ việc lọc FVG và reject lý do ATR nhỏ/không phải Pinbar/VSA volume thấp).*

---
*Antigravity sẵn sàng cho Phase 4 — Vòng lặp OnTick và Quản lý Lệnh thực tế.*



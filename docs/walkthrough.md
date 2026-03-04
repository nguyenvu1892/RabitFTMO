# [Phase 1] Task 1.2 — Phân tích & Kế hoạch Triển khai: MT5 Data Pipeline

> **Tác giả:** Antigravity (AI Coder)
> **Ngày:** 2026-03-05
> **Nhánh:** `feature/task1.2-data-pipeline`
> **Trạng thái:** 🟡 ĐANG CHỜ TECHLEAD DUYỆT — chưa viết code

---

## 1. Tổng quan bài toán

Module `core/data_pipeline.py` phải giải quyết 3 bài toán cốt lõi:

| Bài toán | Mô tả | Rủi ro nếu xử lý sai |
|---|---|---|
| **Kết nối an toàn** | Đọc credentials từ `.env`, không hardcode | Lộ tài khoản FTMO lên Git |
| **Kéo dữ liệu OHLCV** | M5/M15/H1, đủ cột `tick_volume` | Data thiếu → tín hiệu VSA sai |
| **Xử lý Timezone** | Server FTMO trả về UTC; bot Việt Nam ở UTC+7 | Nhầm phiên giao dịch London/NY |

---

## 2. Phân tích thư viện `MetaTrader5` (Python)

### 2.1 Luồng khởi tạo bắt buộc

```python
# Bước 1: Khởi tạo terminal (bắt buộc trước mọi lệnh khác)
mt5.initialize()

# Bước 2: Login tài khoản
mt5.login(login=int, password=str, server=str)

# Bước 3: Kéo data
mt5.copy_rates_from_pos(symbol, timeframe, start_pos, count)

# Bước 4: Đóng kết nối (bắt buộc khi tắt bot)
mt5.shutdown()
```

> ⚠️ **Cạm bẫy quan trọng:** Nếu gọi `mt5.copy_rates_from_pos()` khi chưa `initialize()` hay `login()`, hàm trả về `None` im lặng — KHÔNG raise exception. Phải kiểm tra `None` thủ công.

### 2.2 Cấu trúc dữ liệu trả về

`mt5.copy_rates_from_pos()` trả về một **numpy structured array** với các field:

| Field | Kiểu | Mô tả |
|---|---|---|
| `time` | `int64` | **Unix timestamp (giây) — múi giờ UTC của server** |
| `open` | `float64` | Giá mở nến |
| `high` | `float64` | Giá cao nhất |
| `low` | `float64` | Giá thấp nhất |
| `close` | `float64` | Giá đóng nến |
| `tick_volume` | `int64` | ✅ Tick count — chỉ báo sức mạnh cho VSA |
| `spread` | `int32` | Spread tại thời điểm đóng nến |
| `real_volume` | `int64` | Volume thực (thường = 0 với Forex CFD) |

**Lưu ý VSA:** Với XAGUSD trên MT5/FTMO, `real_volume` hầu như luôn là 0. `tick_volume` là chỉ số proxy volume DUY NHẤT có giá trị — đây là cơ sở của toàn bộ phân tích VSA.

---

## 3. Phân tích vấn đề Timezone (Quan trọng nhất)

### 3.1 Timezone của server FTMO

FTMO sử dụng **UTC+2 (mùa đông) / UTC+3 (mùa hè — DST)**. Tuy nhiên, `mt5.copy_rates_from_pos()` trả về cột `time` dưới dạng **Unix timestamp tuyệt đối** — không bị ảnh hưởng bởi timezone server.

```
Unix timestamp 1709596800 = 2026-03-05 08:00:00 UTC
                          = 2026-03-05 15:00:00 UTC+7 (Hà Nội)
                          = 2026-03-05 10:00:00 UTC+2 (FTMO Winter)
```

### 3.2 Chiến lược xử lý timezone đề xuất

**Lựa chọn được chọn: Lưu trữ UTC, hiển thị UTC — KHÔNG convert sang local time.**

**Lý do:**
1. Bot chạy 24/7, logic trading hoàn toàn dựa trên giờ UTC (London 8am UTC, NY 1pm UTC).
2. Tránh bug DST (Daylight Saving Time) khi Europa chuyển mùa hè/đông — offset thay đổi từ UTC+2 sang UTC+3.
3. Dữ liệu lịch tin tức (ForexFactory) cũng dùng UTC.
4. Pandas `pd.to_datetime(..., unit='s', utc=True)` xử lý đúng và minh bạch.

```python
# ✅ Cách đúng — timezone-aware, lưu UTC
df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)

# ❌ Cách sai — mất thông tin timezone, dễ gây bug phiên
df['time'] = pd.to_datetime(df['time'], unit='s')
```

### 3.3 Bảng đối chiếu phiên giao dịch (UTC)

| Phiên | Giờ UTC | Ý nghĩa |
|---|---|---|
| Tokyo | 00:00 – 08:00 | Ít volume, tránh giao dịch |
| Frankfurt/London | 07:00 – 15:00 | **Phiên vàng — volume cao, SMC setup** |
| New York | 13:00 – 21:00 | **Phiên quan trọng — volatility cao** |
| Overlap LDN-NY | 13:00 – 15:00 | **Cơ hội tốt nhất** |

---

## 4. Thiết kế kiến trúc `MT5DataPipeline`

### 4.1 Sơ đồ class

```
MT5DataPipeline
├── __init__(self)          — Load .env, setup logger
├── connect(self) → bool    — initialize() + login() + validate
├── fetch_data(symbol, timeframe, limit) → DataFrame | None
│   ├── Gọi copy_rates_from_pos()
│   ├── Convert numpy array → DataFrame
│   ├── Convert time column (UTC-aware)
│   ├── Validate cột và dữ liệu
│   └── Return df[['time','open','high','low','close','tick_volume']]
└── disconnect(self)        — mt5.shutdown()
```

### 4.2 Xử lý lỗi có tầng (Layered Error Handling)

```
Tầng 1: Kiểm tra env vars trước khi connect (fail-fast)
         ↓ thiếu MT5_LOGIN/PASSWORD/SERVER → raise EnvironmentError
Tầng 2: Kiểm tra mt5.initialize() thành công
         ↓ thất bại → log lỗi, return False
Tầng 3: Kiểm tra mt5.login() thành công
         ↓ thất bại → log lỗi chi tiết (sai pass vs server không tồn tại), return False
Tầng 4: Kiểm tra mt5.copy_rates_from_pos() không trả về None
         ↓ None → log symbol/timeframe/error_code, return None
Tầng 5: Validate DataFrame có đủ rows và đúng cột
         ↓ thiếu → log warning, return None
```

### 4.3 Lý do dùng `copy_rates_from_pos` thay vì `copy_rates_range`

| Hàm | Tham số | Dùng khi nào |
|---|---|---|
| `copy_rates_from_pos(symbol, tf, start, count)` | `start=0` = nến mới nhất, `count=N` | ✅ **Kéo N nến gần nhất** — phù hợp realtime bot |
| `copy_rates_range(symbol, tf, date_from, date_to)` | Khoảng thời gian cụ thể | Backtest, kéo data lịch sử theo ngày |

Bot Rabit FTMO hoạt động realtime → dùng `copy_rates_from_pos(symbol, tf, 0, limit)`.

---

## 5. Kế hoạch triển khai chi tiết (5 bước)

### Bước 1: Import & Constants
```python
import MetaTrader5 as mt5
import pandas as pd
from dotenv import load_dotenv
import os, logging
from config.settings import SYMBOL, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1, SYSTEM_LOG_FILE
```

### Bước 2: Setup logging ra `logs/system.log`
- Dùng `logging.FileHandler` với `RotatingFileHandler` để log không bị quá lớn.
- Format: `[TIMESTAMP] [LEVEL] [MT5DataPipeline] message`

### Bước 3: Implement `connect()`
```python
def connect(self) -> bool:
    # 1. Load .env
    # 2. Validate env vars (fail-fast)
    # 3. mt5.initialize() — bắt lỗi terminal không mở
    # 4. mt5.login() — bắt lỗi sai pass / sai server
    # 5. Log thông tin tài khoản (account info) để verify
    # 6. return True / False
```

### Bước 4: Implement `fetch_data()`
```python
def fetch_data(self, symbol: str, timeframe, limit: int) -> pd.DataFrame | None:
    # 1. Gọi mt5.copy_rates_from_pos(symbol, timeframe, 0, limit)
    # 2. Kiểm tra kết quả None → log lỗi chi tiết
    # 3. Convert sang DataFrame
    # 4. df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    # 5. Chỉ giữ cột cần thiết: time, open, high, low, close, tick_volume
    # 6. Validate row count và kiểu dữ liệu
    # 7. return df hoặc None
```

### Bước 5: Implement `disconnect()`
```python
def disconnect(self) -> None:
    mt5.shutdown()
    self.logger.info("MT5 connection closed gracefully.")
```

---

## 6. Đề xuất cải tiến — Tối ưu tốc độ & Cache

### 6.1 Vấn đề: Spam request lên MT5

Nếu `strategy_engine.py` gọi `fetch_data()` liên tục mỗi vài giây cho 3 timeframe (M5, M15, H1), sẽ có **~3 request/chu kỳ**. Với chu kỳ 5 giây = **36 request/phút** lên local terminal MT5 — không ảnh hưởng network nhưng tốn CPU.

### 6.2 Giải pháp: In-Memory Cache với TTL (Time-To-Live)

```python
from functools import lru_cache
import time

# Cache đơn giản với TTL tự kiểm tra
_cache = {}
_cache_ts = {}
CACHE_TTL = {
    mt5.TIMEFRAME_M5:  30,   # Cache M5  30 giây (nến 5 phút chưa đóng)
    mt5.TIMEFRAME_M15: 60,   # Cache M15 60 giây
    mt5.TIMEFRAME_H1:  120,  # Cache H1  2 phút
}

def fetch_data(self, symbol, timeframe, limit):
    key = f"{symbol}_{timeframe}_{limit}"
    ttl = CACHE_TTL.get(timeframe, 60)
    if key in _cache and (time.time() - _cache_ts[key]) < ttl:
        return _cache[key].copy()  # Trả về copy để tránh mutation
    # ... kéo data mới
    _cache[key] = df
    _cache_ts[key] = time.time()
    return df.copy()
```

**Lợi ích:** Giảm 90% số lần gọi MT5 API trong chu kỳ ngắn. Đặc biệt quan trọng với H1 (nến 60 phút) — không cần kéo lại mỗi 5 giây.

### 6.3 Cải tiến khác (Phase 2)

| Cải tiến | Mô tả | Priority |
|---|---|---|
| **Reconnect tự động** | Khi `fetch_data` thất bại, thử `connect()` lại 3 lần trước khi raise | 🔴 Cao |
| **Batch fetch** | Kéo 3 timeframe trong 1 lần gọi bằng threading | 🟡 Trung bình |
| **Parquet cache** | Lưu data vào file `.parquet` → restart bot không cần kéo lại | 🟢 Thấp |

---

## 7. Rủi ro và điểm cần TechLead review

> [!WARNING]
> **MT5 Terminal phải đang mở và đăng nhập** khi bot chạy. Nếu terminal bị đóng, `mt5.initialize()` sẽ thất bại ngay cả khi credentials đúng. Bot cần xử lý trường hợp này.

> [!IMPORTANT]
> **Không lưu `MT5_PASSWORD` vào bất kỳ log nào.** Logger phải mask password. Chỉ log `MT5_LOGIN` và `MT5_SERVER`.

> [!NOTE]
> **Symbol XAGUSD phải được enable trong Market Watch của MT5 Terminal.** Nếu symbol không visible, `copy_rates_from_pos` trả về `None`. Cần log thông báo rõ ràng cho user.

---

## 8. File sẽ được tạo/chỉnh sửa

| File | Hành động | Mô tả |
|---|---|---|
| `core/data_pipeline.py` | ✏️ MODIFY | Implement class `MT5DataPipeline` hoàn chỉnh |
| `History.txt` | ✏️ MODIFY | Ghi log Task 1.2 |
| `docs/walkthrough.md` | ✏️ MODIFY | File phân tích này |

---

*Phân tích hoàn tất. Đang chờ TechLead gõ **"PROCEED"** để bắt đầu viết code.*
# Benchmark & Observability Report — Day 14

**Họ tên:** Trần Minh Tân (MSSV: 2A202603688)  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows 11 + WSL2 Ubuntu (Python 3.14.4), Docker Desktop 29.8.2

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | Latency cơ bản của mock LLM ~120–180 ms + retrieval ~20 ms (~200 ms bình thường); ngưỡng 500 ms đảm bảo 95% người dùng nhận phản hồi nhanh ngay cả dưới tải vừa, đồng thời không quá chặt để tránh false alarm khi jitter nhẹ. |
| Error rate `/ask` | < 2.0 % | Mock LLM có tỷ lệ lỗi upstream ~1%; cho phép error budget 2% cho lỗi tạm thời trước khi coi là sự cố cần xử lý. |
| Accuracy trên golden dataset | ≥ 85 % | Đảm bảo agent RAG (`v2`) trả lời đúng phần lớn câu hỏi cốt lõi trong CI quality gate trước khi merge/deploy (mục tiêu sau khi bổ sung KB là 100%). |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

Nguồn dữ liệu: `reports/load_v2_c1.json`, `reports/load_v2_c10.json`, `reports/load_v2_c50.json`, `reports/load_v2_c100.json` (300 requests/mức).

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---:|---:|---:|---:|---:|---|
| 1 | 4.11 | 195.8 | 226.2 | 1706.3 | 1.33% | PASS |
| 10 | 35.88 | 196.9 | 231.5 | 1712.4 | 0.67% | PASS |
| 50 | 92.77 | 220.0 | 519.1 | 1724.9 | 1.00% | FAIL (p95 > 500ms) |
| 100 | 66.38 | 376.6 | 2753.1 | 3024.9 | 0.67% | FAIL (p95 > 500ms) |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ `c=1` lên `c=10`, RPS tăng gần 8.7× (4.11 → 35.88 req/s) với p95 giữ ổn định (~226–231 ms) vì app xử lý async I/O tốt. Từ `c=50` (92.77 req/s, p95 = 519.1 ms) sang `c=100`, RPS lại giảm xuống 66.38 req/s còn p95 nhảy vọt lên 2753.1 ms (p99 = 3024.9 ms) do bão hoà event loop / hàng đợi kết nối và tranh chấp CPU trên 1 process uvicorn local.

### 2.2 Tail latency (`--requests 300 --concurrency 20`)

Nguồn dữ liệu: `reports/load_v2_slow_0.json`, `reports/load_v2_slow_0.03.json`, `reports/load_v2_slow_0.1.json`.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---:|---:|---:|
| 0 | 193.1 | 225.9 | 247.0 |
| 0.03 (mặc định) | 255.4 | 277.9 | 1713.3 |
| 0.1 | 354.0 | 1688.8 | 1720.9 |

**Nhận xét:** `p99` (và `p95` khi tỷ lệ chậm vượt 5% ở mức `0.1`) là chỉ số nhạy nhất với request chậm:
- Khi `MOCK_SLOW_RATE = 0.03` (3% chậm), `avg` chỉ tăng từ 193.1 ms lên 255.4 ms (+62.3 ms), nhưng `p99` nhảy gần 7× từ 247.0 ms lên **1713.3 ms**.
- Khi `MOCK_SLOW_RATE = 0.1` (10% chậm), `avg` mới là 354.0 ms (vẫn dưới 500 ms!), nhưng cả `p95` (**1688.8 ms**) và `p99` (**1720.9 ms**) đều vượt xa SLO 500 ms.
- Vì vậy không nên đặt SLO theo `average`: giá trị trung bình bị 90–97% request nhanh kéo xuống và che giấu trải nghiệm rất tệ ở nhóm tail latency; đặt SLO theo `p95` hoặc `p99` bảo vệ trải nghiệm cho đại đa số người dùng thật.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

Nguồn dữ liệu: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json` (23 câu trong `golden_dataset.jsonl`).

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 58.2 | 109.0 | 113.7 |
| Tổng cost (USD) | $0.000419 | $0.000760 | $0.000790 |
| Cost / câu đúng (USD) | $0.00041895 | $0.00003619 | $0.00003436 |
| Quality gate | FAIL | PASS (≥ 80%) | PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry với từ khoá `["hpa", "kubernetes", "autoscal"]` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích Kubernetes HPA scale theo CPU, memory hoặc custom metrics. |
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry với từ khoá `["jwt"]` vào `KNOWLEDGE_BASE` giải thích sự khác biệt giữa API key cố định và JWT token có chữ ký số và thời điểm hết hạn. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**
- `v1` không có retrieval nên token/câu ít (58.2 tokens) và latency nhanh hơn (p95 = 180.4 ms vs 215.2 ms ở `v2`), nhưng chỉ đúng 1/23 câu (4.3%), dẫn đến **cost / câu đúng lên tới $0.00041895**.
- `v2` tốn gần gấp đôi token (109.0–113.7 tokens/câu) và thêm ~20 ms retrieval, nhưng accuracy tăng lên 91.3% → 100%, làm **cost / câu đúng giảm xuống còn $0.00003436 (rẻ hơn ~12 lần)**.
- **Quality gate trong CI (`.github/workflows/eval.yml`):** Workflow chạy trên `pull_request` vào `main`, bật agent v2 và gọi `python eval/run_eval.py --url http://localhost:8000 --min-accuracy 0.85` (có thể kèm `--baseline`). Khi accuracy < ngưỡng hoặc có regression so với baseline, `run_eval.py` thoát với **exit code 1** (đã kiểm chứng thực tế khi chạy `v1` với `--baseline reports/eval_v2.json` trả `exit code = 1`), làm CI job fail và chặn merge PR.

*(Ghi chú Exercise 7.1: Đã thêm metric Histogram `agent_question_length_chars` trong `develop/app.py`. Trên `/metrics` có các loại metric: Counter như `http_requests_total`, Gauge như `agent_in_flight_requests` / `agent_info`, Histogram như `http_request_duration_seconds` / `agent_question_length_chars`. Dùng `route.path` thay vì `request.url.path` để tránh bùng nổ cardinality khi bot quét hàng nghìn URL ngẫu nhiên.)*

---

## 4. Observability stack (production)

### 4.1 Screenshot & Câu hỏi Exercise 7.4

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals): [grafana-dashboard.png](screenshots/grafana-dashboard.png)
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian): [jaeger-slow-trace.png](screenshots/jaeger-slow-trace.png)
- [x] Một trace lỗi trong Jaeger (có event `exception`): [jaeger-error-trace.png](screenshots/jaeger-error-trace.png)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing**: [prometheus-alert-firing.png](screenshots/prometheus-alert-firing.png)

**Trả lời Exercise 7.4 (số liệu quan sát trực tiếp từ Prometheus / Grafana khi chạy 30 users):**
1. **p95 và avg:** `p95 = 298.6 ms` (trên panel Grafana lúc chụp là `296.55 ms`), `avg = 255.9 ms`, trong khi `p99 ≈ 1.7 s`. Khoảng cách nhỏ giữa `avg` và `p95` cho thấy 95% request đều nhanh (~200–300 ms), nhưng phần chênh lệch vọt lên ở `p99` (~1.7 s) phản ánh ~3% tail latency từ mock LLM.
2. **Requests/s theo instance:** Nginx chia traffic gần như đều nhau cho 2 instance (`172.21.0.5:8000` đạt **9.31 req/s**, `172.21.0.8:8000` đạt **9.56 req/s**) nhờ `upstream agent_cluster` với Docker DNS `resolve`.
3. **Vì sao `input tokens/s` (1438.3/s) lớn hơn `output tokens/s` (752.9/s):** Vì trong pipeline `v2` (RAG), prompt gửi vào LLM gồm `SYSTEM_PROMPT` + tài liệu retrieved từ `KNOWLEDGE_BASE` + câu hỏi của user (~90–100 input tokens), dài gần gấp đôi câu trả lời ngắn gọn đầu ra (~50–55 output tokens).
4. **`curl -i http://localhost:8080/metrics` trả về gì và vì sao:** Trả về **`HTTP/1.1 404 Not Found`**. Trong `production/nginx/nginx.conf`, khối `location = /metrics { return 404; }` chủ động chặn truy cập `/metrics` từ bên ngoài để tránh lộ thông tin nội bộ hệ thống (tải, route, model, cost); chỉ Prometheus trong mạng nội bộ Docker (`obs_net`) mới scrape trực tiếp `agent:8000/metrics`.

### 4.2 Thí nghiệm "phá hệ thống"

Giữ Locust chạy 30 users trong suốt các thí nghiệm:

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`> 5%`, `for: 1m`) | **90 giây** | Golden Signals: Error rate & Requests/s theo status code (`503`) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`p95 > 1s`, `for: 2m`) | **130 giây** | Latency `/ask` — p50 / p95 / p99 |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (`> $2/giờ`, `for: 2m`) | Chuyển `pending` ngay sau khi đổi (tốc độ model large đạt **$20.71/giờ**, gấp ~16×; `for: 2m` → ~125s để firing) | Cost burn rate (USD/giờ) & LLM latency p95 theo model (`495.7 ms`) |
| D | `docker pause` 1 instance (`k5-day14-observability-agent-1`) | `AgentInstanceDown` (`up == 0`, `for: 30s`) | **45 giây** | Golden Signals: Instances (`2 → 1`) & Requests/s theo instance |
| E | `AGENT_VERSION=v1` | **Không có alert nào mới firing** | N/A | Retrieval hit ratio biến mất, Tokens/s giảm ~50% (`input 679.9/s`, `output 369.7/s`), bảng version đổi sang `v1` |

*(Ghi chú thí nghiệm D: Dùng `docker pause` thay vì `docker stop` vì container bị stop sẽ biến mất khỏi Docker DNS nên Prometheus không còn target để đánh `up == 0`; container bị pause vẫn còn trong DNS nhưng không trả `/metrics` → `up == 0`. Lỗi 504 timeout ở Nginx không hiện trên metric của agent vì request chưa được agent xử lý xong để ghi nhận.)*

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Các metric hạ tầng (HTTP status 200, latency, CPU, RAM) đều xanh vì `v1` vẫn trả HTTP 200 nhanh hơn. Để phát hiện suy giảm chất lượng trong production cần:
1. Chạy **automated eval / quality gate** trên golden dataset trong CI/CD trước khi deploy bất kỳ thay đổi `AGENT_VERSION`, prompt hay KB nào.
2. Giám sát **metric nghiệp vụ / chất lượng đặc thù** như `agent_retrieval_total` (hit/miss ratio), cảnh báo khi retrieval miss tăng đột biến hoặc lượng token bất thường.
3. Kết hợp **online evaluation** (LLM-as-a-judge trên một tỷ lệ sample traffic thật) và theo dõi **user feedback** (thumbs up/down, retry rate).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger:

- `trace_id`: `b951475bda2c853408720f322229115f`
- Tổng thời gian: `1716.2 ms` (hiển thị trên Jaeger UI: `1.7s`)
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (`1698.8 ms`, chiếm **99.0%** tổng thời gian; `agent.retrieve_context` chỉ mất `14.8 ms`)
- Dòng log tương ứng (`docker compose -p k5-day14-observability logs agent | grep b951475bda2c853408720f322229115f`):

```json
{"ts": "2026-11-25T07:57:21.843365+00:00", "level": "INFO", "service": "observable-agent", "instance": "9a095d8df3b3", "event": "llm_call", "trace_id": "b951475bda2c853408720f322229115f", "span_id": "475ad0444e27d135", "request_id": "f48519972789", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 95, "output_tokens": 55, "cost_usd": 4.7e-05, "llm_ms": 1698.8}
```

Trace lỗi đối chiếu trong Jaeger ([jaeger-error-trace.png](screenshots/jaeger-error-trace.png)): `trace_id = fc51c39b4c27766ce145cb040a721210` (`status=503`, `ms=91.0`, span `chat mock-llm-small` mất `73.4 ms` với `error.type=upstream_unavailable` và event exception `Upstream LLM error: 503 Service Unavailable (mock)`).

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Nguồn dữ liệu: `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv`.

*(Bảng dưới đây ghi theo dòng `Aggregated` của Locust; trong ngoặc là số liệu riêng của endpoint `POST /ask`.)*

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---:|---:|---:|---:|---|
| 1 | 65.89 (59.75 `/ask`) | 190 | 220 (230 `/ask`) | 1700 | 62 / 7,832 (0.79%; `/ask`: 62 / 7,103 = 0.87%) |
| 3 | 65.66 (59.98 `/ask`) | 190 | 220 (230 `/ask`) | 1700 | 83 / 7,807 (1.06%; `/ask`: 83 / 7,132 = 1.16%) |

**Giải thích kết quả:** Scale từ 1 lên 3 instance **không làm giảm p95/p99** (~220–230 ms / 1700 ms) và RPS giữ nguyên ~65.7 req/s. Lý do:
1. **Nút thắt nằm ở thời gian chờ LLM (`llm_request_duration_seconds`)**: mỗi request chờ bất đồng bộ ~120–180 ms (và 3% request chậm ~1500 ms do `MOCK_SLOW_RATE=0.03`). FastAPI dùng `async/await` nên 1 container xử lý đồng thời rất nhiều coroutine đang chờ I/O mà không nghẽn CPU.
2. **Tải sinh ra bị giới hạn bởi kịch bản user (`wait_time = between(0.5, 2)`)**: 100 user đều đặn nghỉ 0.5–2s giữa các request nên tổng lưu lượng tối đa chỉ khoảng ~65 req/s, chưa chạm ngưỡng CPU của 1 instance.
3. Giá trị của 3 instance trong kiến trúc này là **high availability & headroom**: khi 1 instance gặp sự cố (`docker pause`/crash), 2 instance còn lại vẫn phục vụ không gián đoạn, và khi traffic thực tế tăng cao làm nghẽn CPU/event-loop ở 1 container thì thêm instance mới giúp giữ p95 ổn định.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average che giấu tail latency:** luôn đặt SLO và theo dõi theo `p95`/`p99` thay vì trung bình; chỉ 3% request chậm đã đẩy `p99` lên gần 7× trong khi `avg` trông vẫn ổn.
  2. **Chất lượng và hạ tầng là 2 bài toán tách biệt:** metric hệ thống (latency, status code) không phát hiện được suy giảm độ chính xác như ở thí nghiệm E (`AGENT_VERSION=v1`) — cần eval định kỳ trên golden dataset + quality gate trong CI.
  3. **3 trụ cột Metrics – Traces – Logs liên kết chặt chẽ:** Prometheus/Grafana phát hiện *khi nào* có vấn đề, Jaeger khoanh vùng *bước nào* gây chậm/lỗi (`chat mock-llm-small` 99% thời gian), và `trace_id` nối thẳng sang log JSON chi tiết.
- Nếu đưa agent này lên production thật, nên thêm các metric / alert sau:
  - Alert `LLMBudgetNearLimit` (cảnh báo sớm khi chi tiêu ngày/tháng chạm 80% ngân sách) và metric phân biệt lỗi `429 Rate Limit` vs `402 Budget Exceeded` vs `5xx Upstream`.
  - Giám sát tầng **Load Balancer / Nginx** (tỷ lệ `502`/`504`, `upstream_response_time`) và **synthetic health/ask probes** từ bên ngoài để không bỏ sót lỗi khi agent treo hoàn toàn.
  - Theo dõi **Redis latency / connection errors** và **online eval score / retrieval miss rate** để cảnh báo sớm suy giảm chất lượng RAG.

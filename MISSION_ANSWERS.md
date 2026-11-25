# Day 14 Lab - Mission Answers

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found (`01-localhost-vs-production/develop/app.py`)

Trong file `01-localhost-vs-production/develop/app.py` có ít nhất 7 anti-pattern khiến code không sẵn sàng cho production:

1. **Hardcode secrets trong source code (dòng 17–18):**
   ```python
   OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
   DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
   ```
   Nếu push lên GitHub, secret bị lộ ngay lập tức và nằm vĩnh viễn trong git history.
2. **Hardcode cấu hình, không đọc từ biến môi trường (dòng 21–22):** `DEBUG = True`, `MAX_TOKENS = 500` được gán cứng, không thay đổi được giữa `dev` / `staging` / `production` mà không sửa code.
3. **Dùng `print()` thay cho structured logging và log lộ secret (dòng 33–38):**
   `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` vừa khó parse/filter trong log aggregator, vừa làm lộ trực tiếp API key ra stdout/log.
4. **Không có health check / readiness endpoint (dòng 42–43):** Thiếu `GET /health` và `GET /ready`, nên container orchestrator hoặc cloud platform (Railway, Render, Kubernetes) không biết khi nào process treo để restart hoặc khi nào chưa sẵn sàng nhận traffic.
5. **Bind `host="localhost"` và hardcode `port=8000` (dòng 51–52):**
   - `host="localhost"` chỉ lắng nghe loopback `127.0.0.1`, khi chạy trong Docker container hoặc cloud sẽ không nhận được request từ bên ngoài.
   - `port=8000` cố định không đọc biến `PORT` do cloud platform inject.
6. **Bật `reload=True` trong code chạy chính (dòng 53):** Chế độ auto-reload tốn CPU/file watcher và không ổn định, tuyệt đối không dùng trong production.
7. **Không có lifecycle / graceful shutdown và không có input validation chuẩn:** Thiếu `lifespan` / signal handler cho `SIGTERM` để hoàn thành in-flight requests trước khi tắt, và `/ask` nhận `question: str` qua query parameter thay vì Pydantic JSON body có validation.

### Exercise 1.2: Kết quả chạy bản develop

Chạy `python app.py` trong `01-localhost-vs-production/develop/` và gọi `curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"`:

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:40:02 GMT
server: uvicorn
content-length: 95
content-type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 1.3: So sánh Develop vs Production

Một ví dụ anti-pattern trong `develop/app.py` đã được `production/app.py` (kết hợp `production/config.py`) sửa:
- Ở `develop/app.py` dòng 17–22, 51–52 hardcode `OPENAI_API_KEY`, `host="localhost"`, `port=8000`, `reload=True`. Trong `production/config.py` dòng 15–35, toàn bộ được đọc qua `os.getenv(...)` (như `HOST="0.0.0.0"`, `PORT=8000`, `AGENT_API_KEY`) kèm `Settings().validate()` để fail fast ở production; và ở `production/app.py` dòng 194–199 chạy với `host=settings.host`, `port=settings.port`, `reload=settings.debug`.
- Ở `develop/app.py` không có health check và dùng `print()`, còn `production/app.py` bổ sung `GET /health` (dòng 135–149), `GET /ready` (dòng 152–161), `lifespan` + `SIGTERM` handler (dòng 39–67, 180–189) và log JSON (dòng 28–32, 49–55, 111–122).

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` + `config.py`) | Why Important? |
|---|---|---|---|
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG=True`, `port=8000` | Đọc từ env vars qua `Settings` (`os.getenv`), fail fast nếu thiếu `AGENT_API_KEY` ở production | Tách biệt config khỏi code (12-Factor), không lộ secret lên Git, cùng 1 artifact chạy được ở dev/staging/prod |
| **Network Binding** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port=settings.port` (từ `PORT`), `reload=settings.debug` | `0.0.0.0` cho phép nhận traffic từ bên ngoài container/LB; đọc `PORT` bắt buộc trên Railway/Render |
| **Health & Readiness** | Không có `/health` hay `/ready` | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 khi chưa ready) | Platform biết khi nào container chết để restart và khi nào sẵn sàng để route traffic |
| **Logging** | `print()` text thuần, in cả `OPENAI_API_KEY` | `logging` format JSON, log `event`, `question_length`, `client_ip`, không log secret | Dễ parse/tìm kiếm/cảnh báo trong log aggregator (Loki, Datadog) và đảm bảo an toàn thông tin |
| **Shutdown** | Tắt đột ngột khi process nhận signal | `lifespan` context manager + `signal.signal(SIGTERM, handle_sigterm)` | Cho phép request đang xử lý hoàn thành trước khi tắt, tránh lỗi 502/504 cho người dùng khi deploy |
| **CORS & Input** | Không cấu hình CORS, `question` qua query param | `CORSMiddleware` giới hạn origins, đọc JSON body và validate lỗi 422 | Bảo vệ trình duyệt khỏi cross-origin trái phép và chuẩn hoá contract API |

Kết quả chạy `01-localhost-vs-production/production/app.py`:
- `GET /health` → `200 OK`: `{"status":"ok","uptime_seconds":1.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T07:40:05.173381+00:00"}`
- `GET /ready` → `200 OK`: `{"ready":true}`
- `POST /ask` → `200 OK`: `{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}`

---

## Part 2: Docker

### Exercise 2.1: Dockerfile questions (`02-docker/develop/Dockerfile`)

1. **Base image:** `python:3.11` (bản Debian đầy đủ kèm sẵn Python 3.11 và toàn bộ toolchain/thư viện hệ thống, dung lượng lớn ~1 GB+).
2. **Working directory:** `/app` (đặt bằng `WORKDIR /app` — mọi lệnh `COPY`, `RUN`, `CMD` sau đó thực thi tương đối từ `/app`).
3. **Tại sao `COPY requirements.txt` trước `COPY app.py` / `COPY . .`:** Docker build theo từng layer và cache các layer không đổi. `requirements.txt` ít thay đổi hơn source code; nếu copy và `pip install` trước, khi sửa code (`app.py`), Docker tái sử dụng cache layer cài packages thay vì tải và cài lại toàn bộ thư viện mỗi lần build.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào:**
   - `ENTRYPOINT` định nghĩa executable cố định luôn chạy khi container start (tham số truyền thêm sau `docker run <image> ...` được nối vào làm argument cho entrypoint).
   - `CMD` định nghĩa lệnh mặc định hoặc tham số mặc định cho `ENTRYPOINT`, và dễ dàng bị ghi đè khi truyền command lúc `docker run <image> <custom_cmd>`.

### Exercise 2.2: Build và run container bản develop

Build từ gốc repo: `docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`  
Chạy container `docker run -d --rm --name p2-dev-test -p 8000:8000 my-agent:develop` và test `curl -sS -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"`:

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:41:43 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: Multi-stage build & Image size comparison

Trong `02-docker/production/Dockerfile`:
- **Stage 1 (`builder`):** Dùng `python:3.11-slim`, cài compiler/build tools (`gcc`, `libpq-dev`) và chạy `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime`):** Bắt đầu lại từ `python:3.11-slim` sạch, tạo user non-root `appuser`, chỉ `COPY --from=builder /root/.local /home/appuser/.local` và source code cần chạy (`main.py`, `utils/mock_llm.py`), thêm `HEALTHCHECK`, chạy `uvicorn` dưới quyền `appuser`.
- **Tại sao image nhỏ hơn:** Không mang theo `gcc`, `libpq-dev`, headers, pip cache hay các file trung gian của stage `builder` vào image cuối; đồng thời dùng base `-slim` thay vì full `python:3.11`.

Kết quả đo trực tiếp bằng `docker images` và `docker image inspect`:
- **Develop (`my-agent:develop`):** `1.67 GB` (`1,667,775,791 bytes` ≈ **1,667.8 MB**)
- **Production (`my-agent:advanced`):** `240 MB` (`239,815,290 bytes` ≈ **239.8 MB**)
- **Chênh lệch (giảm):** giảm **1,428.0 MB**, nhỏ hơn **85.6%** so với bản develop.

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

Các service được start: `agent` (FastAPI), `redis` (`redis:7-alpine`), `qdrant` (`qdrant/qdrant:v1.9.0`), `nginx` (`nginx:alpine`). Tất cả giao tiếp qua mạng nội bộ `internal`, chỉ `nginx` mở port `80`/`443` ra ngoài; `agent` chờ `redis` và `qdrant` đạt `service_healthy` qua `depends_on`.

Sơ đồ kiến trúc:
```text
Client
  │  (HTTP :80)
  ▼
Nginx (nginx:alpine, rate limit 10 req/s, security headers)
  │  (proxy_pass http://agent:8000, network: internal)
  ▼
Agent (FastAPI, port 8000, HEALTHCHECK /health)
  ├──▶ Redis (:6379, session cache & rate limiting)
  └──▶ Qdrant (:6333, vector database cho RAG)
```

Kết quả test qua Nginx (`http://localhost`):
- `curl -sS -i http://localhost/health`:
  ```http
  HTTP/1.1 200 OK
  Server: nginx
  Content-Type: application/json
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  X-XSS-Protection: 1; mode=block

  {"status":"ok","uptime_seconds":0.8,"version":"2.0.0","timestamp":"2026-11-25T07:42:06.398135"}
  ```
- `curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'`:
  ```http
  HTTP/1.1 200 OK
  Server: nginx
  Content-Type: application/json

  {"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
  ```

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy Agent Part 6 lên Cloud & So sánh `railway.toml` vs `render.yaml`

- **URL public (Agent Part 6):** `<PENDING_CLOUD_DEPLOY_URL>` *(cập nhật ngay sau bước deploy ở CP6)*
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

**So sánh `railway.toml` vs `render.yaml`:**

| Tiêu chí | `railway.toml` | `render.yaml` |
|---|---|---|
| **Định dạng & Phạm vi** | TOML, cấu hình cho **1 service** (build & deploy settings cho service hiện tại). | YAML (Blueprint IaC), mô tả được **nhiều service cùng lúc** (web service + managed Redis add-on trong cùng 1 file). |
| **Build / Runtime** | Khai báo `builder = "DOCKERFILE"` (hoặc `"NIXPACKS"`). | Khai báo `runtime: docker` (hoặc `runtime: python` kèm `buildCommand` + `startCommand`). |
| **Health check** | `[deploy] healthcheckPath = "/health"` và `healthcheckTimeout`. | `healthCheckPath: /health` trên từng web service. |
| **Biến môi trường & Secrets** | Thường set qua Railway Dashboard / `railway variables set` chứ không khai báo secret trong `railway.toml`. | Khai báo trực tiếp `envVars` trong file; secret dùng `generateValue: true` (Render tự sinh) hoặc `sync: false` (nhập tay trên dashboard), có thể nối `REDIS_URL` qua `fromService`. |
| **Lý do khác nhau** | Railway thiết kế theo hướng service-centric, tự động inject env và thêm database/Redis bằng plugin trên project. | Render Blueprint theo hướng declarative full-stack IaC cho phép version-control toàn bộ topology (app + Redis + env wiring) trong một file duy nhất. |

### Exercise 3.3: GCP Cloud Run CI/CD (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên `main` đi qua 4 bước tuần tự (`waitFor`):
1. **Test (`test`):** Dùng image `python:3.11-slim` để cài dependencies từ `requirements.txt` và chạy `pytest tests/ -v --tb=short`.
2. **Build (`build`):** Dùng `gcr.io/cloud-builders/docker` build image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from` để cache layer).
3. **Push (`push`):** Đẩy cả hai tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **Deploy (`deploy`):** Dùng `gcloud run deploy ai-agent` để rollout image `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình `min-instances=1`, `max-instances=10`, `512Mi` RAM, `1` CPU, gắn biến môi trường và secret (`--set-secrets` từ Secret Manager). File `service.yaml` là bản khai báo IaC Knative tương ứng, định nghĩa `containerConcurrency: 80`, `livenessProbe` (`/health`) và `startupProbe` (`/ready`).

---

## Part 4: API Security

### Exercise 4.1: API Key authentication (`04-api-gateway/develop/app.py`)

- **API key được check ở đâu:** Trong dependency `verify_api_key(api_key: str = Security(api_key_header))` (dòng 39–54) đọc header `X-API-Key` bằng `APIKeyHeader(name="X-API-Key", auto_error=False)`, được gắn vào `/ask` qua `_key: str = Depends(verify_api_key)` (dòng 70).
- **Nếu thiếu hoặc sai key:** Thiếu header trả `401 Unauthorized` (`Missing API key...`); có header nhưng khác `API_KEY` trả `403 Forbidden` (`Invalid API key.`).
- **Cách rotate key:** Không hardcode key trong code mà đọc `AGENT_API_KEY` từ biến môi trường (`os.getenv("AGENT_API_KEY", ...)`). Khi rotate key: hỗ trợ chấp nhận song song cả key cũ và key mới (vd `AGENT_API_KEYS=key_new,key_old`) trong giai đoạn chuyển tiếp để client cập nhật, sau đó gỡ key cũ khỏi env var và restart/redeploy.

Kết quả test với `AGENT_API_KEY=secret-key-123 python app.py`:

- **Không có key (`401`):**
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 07:40:07 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

- **Có key đúng (`200`):**
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:40:07 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"Hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT authentication & Rate limiting (`04-api-gateway/production/`)

Trả lời câu hỏi `rate_limiter.py`:
- **Algorithm:** **Sliding Window Counter** (lưu `deque` chứa timestamps các request của từng `user_id` trong cửa sổ 60 giây, xoá timestamps cũ hơn `now - window_seconds` rồi đếm `len(window)`).
- **Giới hạn:** `rate_limiter_user` = **10 requests / 60 giây** (`student` có `role="user"`); `rate_limiter_admin` = **100 requests / 60 giây** (`teacher` có `role="admin"`).
- **Cách bypass / nới limit cho admin:** Trong `app.py` dòng 141 kiểm tra `role = user["role"]` giải mã từ JWT (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`). Muốn admin bypass hoàn toàn chỉ cần bỏ qua bước `limiter.check(...)` khi `role == "admin"`.

Kết quả test với tài khoản `student` / `demo123` (`POST /auth/token`, token đã được che `<REDACTED_TOKEN>`):

- **Không gửi Bearer token (`401`):**
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 07:40:09 GMT
server: uvicorn
www-authenticate: Bearer
content-length: 76
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

- **Có JWT hợp lệ (`200`):**
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 07:40:09 GMT
server: uvicorn
content-length: 184
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Explain JWT","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

- **Vòng lặp gọi liên tục vượt 10 req/phút (`429`):**
```text
req 1 -> HTTP 200
req 2 -> HTTP 200
req 3 -> HTTP 200
req 4 -> HTTP 200
req 5 -> HTTP 200
req 6 -> HTTP 200
req 7 -> HTTP 200
req 8 -> HTTP 200
req 9 -> HTTP 200
req 10 -> HTTP 429
```
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 07:40:10 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795592471
retry-after: 59
content-length: 98
content-type: application/json

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```
*(Ghi chú: 1 request `200` trước vòng lặp + 9 request `200` đầu vòng lặp = đủ 10 requests trong cửa sổ 60s, nên request thứ 10 của vòng lặp lập tức bị chặn với `429 Too Many Requests` và header `Retry-After: 59`.)*

### Exercise 4.4: Cost guard implementation (`04-api-gateway/production/cost_guard.py` & Part 6)

- **Tại sao cần cả Rate Limit và Cost Guard:** Rate limit giới hạn **tốc độ gọi** (số request/phút) để chống spam/DoS, nhưng không chặn được việc kẻ xấu gửi nhiều câu hỏi rất dài hoặc chạy đều đặn trong ngày gây đội chi phí token LLM. Cost guard bảo vệ **ngân sách tiền** (USD/ngày hoặc USD/tháng).
- **Cách hoạt động (`cost_guard.py`):**
  - Trước khi gọi LLM, `check_budget()` kiểm tra tổng chi phí đã dùng so với ngưỡng (`daily_budget_usd = $1.0` per user → trả **402 Payment Required**; `global_daily_budget_usd = $10.0` → trả **503**; đạt 80% budget → ghi log warning).
  - Sau khi LLM trả lời, `record_usage()` / `record_cost()` tính chi phí từ `input_tokens` và `output_tokens` theo đơn giá model (`$0.00015 / 1K input`, `$0.0006 / 1K output`) rồi cộng dồn vào bộ đếm theo ngày/tháng.
  - Ở bản production (Part 6), tổng chi phí được lưu trong **Redis** bằng `INCRBYFLOAT` trên key theo ngày/tháng (`cost:daily:YYYY-MM-DD`, `cost:monthly:YYYY-MM`) kèm `EXPIRE` để mọi worker/instance dùng chung và không mất khi restart.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health checks & Graceful shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - `GET /health` (Liveness): trả `200 OK` khi process còn sống (không nên phụ thuộc vào Redis/DB ngoài để tránh việc Redis chập chờn khiến orchestrator restart hàng loạt container). Nếu `/health` lỗi, platform restart container.
  - `GET /ready` (Readiness): kiểm tra agent đã khởi tạo xong và kết nối phụ thuộc (Redis, DB) sẵn sàng chưa. Nếu chưa sẵn sàng hoặc đang shutdown (`_is_ready = False`), trả `503 Service Unavailable` để Load Balancer tạm ngừng gửi traffic mới vào instance này mà không kill container.
- **Graceful shutdown (`SIGTERM`):**
  Khi gửi `kill -TERM <pid>` trong lúc request `POST /ask?question=Long%20task` đang chạy:
  1. `uvicorn` nhận `SIGTERM`, ngừng nhận kết nối mới và gọi `lifespan` shutdown.
  2. `_is_ready` chuyển thành `False` (`/ready` trả 503), app chờ `_in_flight_requests` về 0.
  3. Request đang chạy vẫn hoàn thành và trả `HTTP/1.1 200 OK`, sau đó server mới thoát sạch:
  ```text
  INFO:     Shutting down
  INFO:     127.0.0.1:56276 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
  INFO:     Waiting for application shutdown.
  2026-11-25 14:40:16,935 INFO 🔄 Graceful shutdown initiated...
  2026-11-25 14:40:16,935 INFO ✅ Shutdown complete
  INFO:     Finished server process [490]
  2026-11-25 14:40:16,936 INFO Received signal 15 — uvicorn will handle graceful shutdown
  ```

### Exercise 5.3, 5.4 & 5.5: Stateless design & Load balancing (`05-scaling-reliability/production/`)

- **Vì sao state trong RAM bị hỏng khi scale nhiều instance:** Mỗi container/instance có bộ nhớ RAM riêng biệt. Nếu lưu session/conversation history trong dict trên RAM, Request 1 của User A vào Instance 1 được lưu ở RAM Instance 1, nhưng Request 2 do Nginx round-robin sang Instance 2 sẽ không thấy session đó. Khi lưu vào **Redis** (`session:{session_id}` kèm TTL), mọi instance đều đọc/ghi chung một nguồn dữ liệu nên hệ thống hoàn toàn stateless.
- Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` (mở port `8080`, endpoint `POST /chat`) rồi chạy `python test_stateless.py`:

```text
============================================================
Stateless Scaling Demo
============================================================

Session ID: 2fb7902e-a7e4-4877-a6b2-3fef827ac433

Request 1: [instance-73eb7d]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-3fafaa]
  Q: Why do we need containers?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 3: [instance-73eb7d]
  Q: What is Kubernetes?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 4: [instance-1fd18a]
  Q: How does load balancing work?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 5: [instance-3fafaa]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-1fd18a', 'instance-73eb7d', 'instance-3fafaa'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Kubernetes?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: How does load balancing work?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```

5 request được Nginx chia qua cả 3 container instance (`instance-73eb7d`, `instance-3fafaa`, `instance-1fd18a`), nhưng `GET /chat/{session_id}/history` vẫn đọc đủ 10 message (5 câu hỏi + 5 câu trả lời) do toàn bộ lịch sử được lưu tập trung trong Redis.

---

## Part 6: Final Project — `check_production_ready.py` Output

Chạy `python check_production_ready.py` trong `06-lab-complete/` (môi trường WSL2 Ubuntu POSIX + Docker 29.8.2):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

- Kích thước image Part 6 đo được: **238 MB** (< 500 MB).
- `docker stop`: **exit code 0, 0.6s** (< 10s).

---

## AI log

1. **Part 6 — Triển khai các TODO trong `06-lab-complete/`:**
   - *Hỏi gì:* Thiết kế và hoàn thiện các module `config.py`, `auth.py`, `redis_client.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile` multi-stage, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml` theo đúng hợp đồng trong `06-lab-complete/README.md`.
   - *Nhận gì:* Gợi ý cài đặt sliding-window rate limiter bằng Redis sorted set với member chứa UUID để tránh trùng timestamp khi chạy 2 worker, lưu lại handler `SIGTERM` gốc của uvicorn trước khi đăng ký log handler, và đặt `PYTHONUSERBASE=/home/appuser/.local` trong multi-stage Dockerfile.
   - *Tự sửa & tự kiểm tra:* Bổ sung `socket_connect_timeout=1.0` trong `redis_client.py` để `/ready` trả 503 tức thì khi Redis mất kết nối; chạy đầy đủ `python check_production_ready.py` trong WSL2 đạt `PASS 12/12 (43/43 checks passed)`.
2. **Part 1–5 — Chạy kiểm chứng và tổng hợp giải thích:**
   - *Hỏi gì:* Đối chiếu các anti-pattern ở `01-localhost-vs-production`, so sánh `railway.toml` và `render.yaml`, phân tích pipeline `cloudbuild.yaml`/`service.yaml`.
   - *Nhận gì:* Bảng tổng hợp các tiêu chí 12-Factor, cơ chế sliding-window trong `rate_limiter.py` và cấu trúc multi-stage Docker.
   - *Tự sửa & tự kiểm tra:* Tự chạy toàn bộ server và stack Docker mẫu (`01` develop/production, `02` docker build & compose, `04` API key & JWT rate limit 429, `05` `--scale agent=3` + `test_stateless.py`), tự đo kích thước image (`1.67 GB` vs `240 MB`) và dán kết quả thực tế vào bài.

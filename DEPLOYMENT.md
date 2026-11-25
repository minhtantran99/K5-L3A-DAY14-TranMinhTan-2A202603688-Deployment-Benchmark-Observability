# Deployment Information

## Public URL
https://agent-production-0643c5b4.up.railway.app

## Platform
Railway (`06-lab-complete/` deployed via Dockerfile + managed Redis service)

## Test Commands

### Health Check (Liveness)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-0643c5b4.up.railway.app/health"
# Expected: 200
# Body: {"status":"ok","environment":"production"}
```

### Readiness Check (Redis Connected)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://agent-production-0643c5b4.up.railway.app/ready"
# Expected: 200
# Body: {"status":"ready"}
```

### Auth Check (Missing API Key)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "https://agent-production-0643c5b4.up.railway.app/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401
```

### API Test (With Authentication)
```bash
curl -sS -X POST "https://agent-production-0643c5b4.up.railway.app/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "What is deployment?"}'
# Expected: 200
```

### Production Readiness Check
```bash
cd 06-lab-complete
python check_production_ready.py --public-url https://agent-production-0643c5b4.up.railway.app
# Result: PASS 12/12 (44/44 checks passed)
```

## Environment Variables Set
- `PORT` (injected automatically by Railway: `8080`)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — internal Railway Redis reference)
- `AGENT_API_KEY` (configured securely in Railway Variables)
- `ENVIRONMENT` (`production`)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `MONTHLY_BUDGET_USD` (`10.0`)
- `LOG_LEVEL` (`INFO`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)

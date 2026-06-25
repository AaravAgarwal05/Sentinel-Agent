# Required Updates

## Heartbeat Improvements

### Problem
Heartbeat scheduler runs in mock mode — every tick logs a "mock_heartbeat_tick" message but never makes an HTTP call. The control plane has no visibility into whether agents are alive.

### Files to change

#### 1. `~/SentinelAI-v1/services/api_service/api_service.py`
Add `POST /agent/heartbeat` endpoint:

```python
@router.post("/agent/heartbeat")
def agent_heartbeat(payload: AgentHeartbeat):
    # Accept: cluster_id, agent_version, status, timestamp
    # Persist or update agent's last_seen
    pass
```

Need new Pydantic model `AgentHeartbeat` in a shared module.

#### 2. `charts/sentinel-agent/values.yaml`
```yaml
sentinel:
  apiUrl: http://172.18.0.3:30586   # was https://api.sentinel.example.com
  mockMode: false                     # was true

heartbeat:
  intervalSeconds: 60                 # was 30
```

#### 3. `charts/sentinel-agent/templates/configmap.yaml`
Ensure `SENTINEL_API_URL` and `SENTINEL_MOCK_MODE` env vars derive from the above values.

#### 4. `agent/config/settings.py`
Verify `HeartbeatConfig` / `SentinelConfig` read the env vars correctly when mock mode is off.

#### 5. Rebuild & redeploy both sides
```
# sentinel-api
docker build -t sentinel-api:latest ~/SentinelAI-v1
kind load docker-image sentinel-api:latest --name sentinel
kubectl rollout restart deployment -n sentinel

# sentinel-agent
docker build -t sentinel-agent:latest ~/Sentinel-Agent
kind load docker-image sentinel-agent:latest --name target
kubectl rollout restart deployment -n sentinel-agent
```

---

## Transport Pipeline (already fixed)

### Changes applied in this session
- `agent/transport/client.py` — flat payload, skip Bearer when key is empty
- `agent/transport/service.py` — `_build_payload()` returns only `Incident`-model fields
- `agent/detection/service.py` — fallback DiagnosticReport when analyzer returns None
- `agent/runtime/runtime_manager.py` — start RetryService background loop
- `charts/sentinel-agent/values.yaml` — NodePort URL for cross-cluster
- `charts/sentinel-agent/templates/configmap.yaml` — transport env vars

### Remaining transport issues (lower priority)

| Issue | Impact | Mitigation |
|-------|--------|------------|
| SQLite in ephemeral pod loses PENDING reports on restart | Reports in-flight are lost if pod restarts | Use PVC for SQLite or switch to agent-side queue |
| No idempotency key | Same incident could be delivered twice on retry | Add `incident_id` as idempotency key on sentinel-api |
| No dead-letter queue | FAILED reports go nowhere after max_retries | Add DLQ table or alert on FAILED count |

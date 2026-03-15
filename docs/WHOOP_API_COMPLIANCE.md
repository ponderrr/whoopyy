# WHOOP API - Rate Limits & Compliance Rules

## 🚦 RATE LIMITS (DEFAULT)

### Per-Minute Limit
- **100 requests per 60 seconds**
- Window: Rolling 60-second period
- Reset: Tracked via `X-RateLimit-Reset` header

### Per-Day Limit  
- **10,000 requests per 24 hours (86,400 seconds)**
- Window: Rolling 24-hour period
- Total daily cap across all endpoints

### Rate Limit Headers

Every API response includes:

```
X-RateLimit-Limit: "100, 100;window=60, 10000;window=86400"
X-RateLimit-Remaining: "98"
X-RateLimit-Reset: "3"
```

**Header Breakdown:**
- `X-RateLimit-Limit`: Shows all active limits and time windows
- `X-RateLimit-Remaining`: Requests left in closest-to-exceeded window
- `X-RateLimit-Reset`: Seconds until closest limit resets

### 429 Response

When rate limit exceeded:
```json
{
  "message": "Too Many Requests"
}
```

HTTP Status: `429 Too Many Requests`

---

## 📊 DATA SIZE ESTIMATES

**Per Day of User Data:**
- 1 workout + 1 sleep + 1 recovery ≈ **4 KB**
- 30 days ≈ **120 KB**
- 365 days ≈ **1.46 MB**

This is minimal - rate limits are the primary constraint, not bandwidth.

---

## ✅ COMPLIANCE REQUIREMENTS

### 1. OAuth 2.0 Authentication
- **Required for all API access**
- Access tokens expire every **1 hour**
- Must implement automatic token refresh
- Use `offline` scope for long-term access (refresh tokens)

### 2. Required Scopes

Request **only the scopes you need:**

| Scope | Access |
|-------|--------|
| `read:profile` | Basic profile (name, email) |
| `read:body_measurement` | Height, weight, max HR |
| `read:cycles` | Daily physiological cycles |
| `read:recovery` | Recovery scores, HRV, resting HR |
| `read:sleep` | Sleep stages, performance, quality |
| `read:workout` | Workout history, strain, metrics |

**Do NOT request all scopes** - limit to what your app actually uses.

### 3. WHOOP Membership Required
- **You must have an active WHOOP device/membership** to develop
- API access is free, but membership is required
- This ensures developers understand the user experience

### 4. App Approval Process
- Apps must be **submitted for approval** before public launch
- WHOOP reviews:
  - Scopes requested (are they necessary?)
  - Privacy policy compliance
  - Data handling practices
  - User experience alignment with WHOOP brand

### 5. No Constant Polling
- Use **webhooks** for real-time data updates
- Avoid polling endpoints every few seconds
- Cache data appropriately
- Webhooks prevent unnecessary API calls

---

## 🎯 BEST PRACTICES FOR OUR APP

### Rate Limit Strategy

**1. Server-Side Caching**
```typescript
// Cache recovery data for 1 hour (data doesn't change that fast)
// Cache sleep data for 6 hours (sleep is overnight, static during day)
// Cache workout data for 15 minutes (user might log new workouts)
```

**2. Batch Requests Intelligently**
```typescript
// Good: Fetch last 7 days on initial load, cache results
const recoveries = await client.get_recovery_collection(limit=7)

// Bad: Fetch each day individually in a loop
for (let i = 0; i < 7; i++) {
  const recovery = await client.get_recovery(date=...) // 7 API calls!
}
```

**3. Handle 429 Gracefully**
```typescript
try {
  const data = await fetchWhoopData()
} catch (error) {
  if (error.status === 429) {
    const retryAfter = parseInt(error.headers['X-RateLimit-Reset'])
    // Wait retryAfter seconds before retry
    // Show user: "Rate limit reached. Retrying in {retryAfter} seconds..."
  }
}
```

**4. Use Webhooks (Future Enhancement)**
- Register for webhook events: `recovery.updated`, `sleep.created`, `workout.created`
- Your server receives events instantly (no polling needed)
- Only fetch data when actually changed

### Request Budget Planning

**Typical Dashboard Load:**
```
Initial Page Load:
- 1 request: User profile
- 1 request: Body measurements
- 1 request: Recovery collection (last 7 days)
- 1 request: Sleep collection (last 7 days)
- 1 request: Cycle collection (last 7 days)
- 1 request: Workout collection (last 7 days)
───────────────────────────────────
Total: 6 requests

With Server-Side Caching (1-hour TTL):
- User loads page: 6 requests (cache MISS)
- User refreshes: 0 requests (cache HIT)
- After 1 hour: 6 requests (cache expired)
───────────────────────────────────
Daily Total (assuming 10 daily visits): ~60 requests
```

**This is WELL within limits:**
- Per-minute: 60 requests / 1,440 minutes = **0.04 requests/min** (100 allowed)
- Per-day: **60 requests** (10,000 allowed)

**Conclusion:** With proper caching, we'll use **less than 1%** of our rate limit.

---

## 🔐 SECURITY & PRIVACY

### Token Storage
- **NEVER expose client_secret in frontend code**
- Store access/refresh tokens securely (server-side only)
- Use environment variables for credentials
- Implement token rotation/refresh logic

### User Data Privacy
- Only fetch data for authenticated user
- Don't store unnecessary historical data
- Comply with GDPR/CCPA if applicable
- Provide data export/deletion features

### Error Handling
- Don't expose raw API errors to users
- Log errors server-side for debugging
- Show user-friendly messages:
  - "Unable to load data. Please try again."
  - "Rate limit reached. Refreshing in 30 seconds..."

---

## 📋 PRE-LAUNCH CHECKLIST

Before deploying to production:

- [ ] Rate limit handling implemented (429 errors)
- [ ] Token refresh logic working (1-hour expiration)
- [ ] Server-side caching configured (Redis/Vercel KV)
- [ ] Only necessary scopes requested
- [ ] Privacy policy created and linked
- [ ] Client credentials secured (not in frontend)
- [ ] Error messages user-friendly
- [ ] WHOOP app submitted for approval
- [ ] Webhook integration planned (future)
- [ ] Monitoring/logging configured

---

## 🚀 RATE LIMIT INCREASE REQUESTS

If we exceed default limits in the future:

**When to request:**
- Consistent 429 errors
- Legitimate use case for higher limits
- Growing user base requiring more requests

**How to request:**
- Submit via: [WHOOP Rate Limit Request](https://developer.whoop.com/docs/developing/rate-limiting/)
- Include:
  - Current usage patterns
  - Expected growth
  - Specific limits needed (per-minute and per-day)
  - Use case description

**What to expect:**
- WHOOP reviews on case-by-case basis
- May grant tiered increases
- Webhook usage demonstrates good API citizenship

---

## 📚 REFERENCES

- [Rate Limiting Docs](https://developer.whoop.com/docs/developing/rate-limiting/)
- [API Reference](https://developer.whoop.com/api/)
- [OAuth Guide](https://developer.whoop.com/docs/developing/oauth/)
- [Getting Started](https://developer.whoop.com/docs/developing/getting-started/)

---

## ✅ COMPLIANCE SUMMARY

**We are compliant if:**
1. ✅ Use OAuth 2.0 with automatic token refresh
2. ✅ Request only necessary scopes
3. ✅ Implement server-side caching (1-6 hour TTL)
4. ✅ Handle 429 errors gracefully with retry logic
5. ✅ Store credentials securely (server-side only)
6. ✅ Submit app for approval before public launch
7. ✅ Stay well under 100 req/min and 10K req/day limits
8. ✅ Plan webhook integration to minimize polling

**Current Risk Level:** 🟢 **LOW** - Our dashboard usage pattern (~60 req/day with caching) is <1% of limits.

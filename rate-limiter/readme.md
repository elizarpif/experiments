## Redis Rate Limiter

How to implement a rate-limiter?

### Requirements
1. **Limit**: 2 requests per minute for 1 `user_id`.
2. **Restriction Strategy**: `user_id` or `IP`?
    * **Restrict by IP**: Best for unauthenticated services. (Can be implemented via Nginx using `limit_req_zone` with `$binary_remote_addr`).
    * **Restrict by User ID**: Best for authenticated services. (Can be implemented via API Gateways like AWS API Gateway; note that in development, `X-User-ID` can be easily mocked).

> **Hybrid Approach**: Use IP limiting to prevent DDoS and `user_id` limiting for application-level rate management.

---

### Redis Challenges
1. **Race Conditions**: Use `MULTI/EXEC` transactions or **Lua scripts** for distributed backends. 
    * *Note*: Not strictly required if using a **Fixed Window** approach with a timestamp in the key.
2. **High Availability**: If Redis goes down, use **Redis Read Replicas** or a local **in-memory cache** (potentially with distributed sharding/consistent hashing).
3. **Subscription Tiers**: For different user levels, use a **composite key** or fetch the user's limit dynamically and apply it to the `user_id` key.

---

### Algorithms: Which one to choose?
1. **Fixed Window**: Simplest to implement; allows a "double burst" at the edge of the time window.
2. **Token Bucket**: The "golden standard"; allows controlled burstiness.
3. **Leaking Bucket**: Processes requests at a constant, smooth rate.
4. **Sliding Window Log**: Stores timestamps for every request; highly accurate but memory-intensive.
5. **Sliding Window Counter**: Calculates a weighted average between the current and previous window.

---

### Run
Launch two instances to test distributed behavior:
```bash
go run main.go -port=3000
go run main.go -port=3001
```

Test a specific user:
```bash
curl -i -H "X-User-Id: 123" http://localhost:3000
```

---

### Nginx Configuration
To test the IP-based limit, update your config (e.g., `/opt/homebrew/etc/nginx/nginx.conf`):

```nginx
http {
    # $binary_remote_addr = client IP
    # zone=mylimit:10m = 10MB of shared memory to track IPs
    # rate=1r/m = Allow 1 request per minute
    limit_req_zone $binary_remote_addr zone=mylimit:10m rate=1r/m;

    # Define Go instances (Load Balancing)
    upstream my_go_app {
        server 127.0.0.1:3000;
        server 127.0.0.1:3001;
    }

    server {
        listen 80; 
        server_name localhost;

        location / {
            # burst=5 = Allow a small burst of 5 requests
            # nodelay = Reject immediately if over burst capacity
            limit_req zone=mylimit burst=5 nodelay;
            limit_req_status 429;

            # Proxy traffic to the Go upstream
            proxy_pass http://my_go_app;
            
            # Pass real IP to the backend
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-User-Id $http_x_user_id;
        }
    }
}
```
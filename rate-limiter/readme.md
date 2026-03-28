## redis

How to implement rate-limiter?

requirements:
1) 2 requests per minute for 1 user-id
2) how to restrict? user_id or ip?
- restrict by IP is the best way for unathenticated services (can be done with Nginx - Use Nginx limit_req_zone to rate limit by $binary_remote_addr.)
- restrict by user_id is the best way for authentificated services (can be done with API gateways - like AWS API gateway, in realworld X-User-ID can be easily mocked)

Hybrid Approach: Use IP limiting to prevent DDoS, and User ID limiting for application-level rate management.


Redis problems:
1) race condition - we can use transactions or lua script for distributed backend // no need if we create a key with a timestamp (Fixed window)


### run
`go run main.go -port=3001`
`go run main.go -port=3000`

```bash
curl -iH "X-User-Id: 123" http://localhost:3001
```

for nginx check, fix this config `/opt/homebrew/etc/nginx/nginx.conf`
```nginx
http {
    # $binary_remote_addr = client IP
    # zone=mylimit:10m = 10MB of memory to track IPs
    # rate=1r/m = Allow 1 request per minute
    limit_req_zone $binary_remote_addr zone=mylimit:10m rate=1r/m;

    # define Go instances (Load Balancing)
    upstream my_go_app {
        server 127.0.0.1:3000;
        server 127.0.0.1:3001;
    }

    server {
        listen 80; # Nginx will now listen on port 80
        server_name localhost;

        location / {
            # burst=5 = Allow a small burst of 5 requests
            # nodelay = Don't make the user wait; reject immediately if over burst
            limit_req zone=mylimit burst=5 nodelay;
            limit_req_status 429;

            # Proxy the traffic to your Go apps
            proxy_pass http://my_go_app;
            
            # Pass the real IP to Go (so Go logs show the user, not Nginx)
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }
    }
}
```
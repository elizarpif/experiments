```bash
uvicorn main:app --reload --port 8000

sudo systemctl enable cloudflared-tunnel
sudo systemctl start cloudflared-tunnel

sudo journalctl -u cloudflared-tunnel -n 25 --no-pager


sudo systemctl status reader
sudo systemctl restart reader
```


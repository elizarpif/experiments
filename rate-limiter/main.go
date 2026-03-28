package main

import (
	"fmt"
	"log"
	"net/http"
	"time"

	"flag"

	redis "github.com/redis/go-redis/v9"
)

func main() {
	port := flag.String("port", "8080", "The port to listen on")

	flag.Parse()

	handlerClient := newHandlerClient()

	mux := http.NewServeMux()

	mux.Handle("GET /", handlerClient.middleware(messageHandler()))

	log.Printf("listening on :%s...", *port)

	err := http.ListenAndServe(fmt.Sprintf(":%s", *port), mux)
	if err != nil {
		log.Fatal(err)
	}
}

func messageHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		userID := r.Header.Get("X-User-Id")

		fmt.Fprintf(w, "got message from user %s", userID)
	})
}

const limit = 2

func (c *handlerClient) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		timeNow := time.Now().UTC().Format("2006-01-02T15:04")
		userID := r.Header.Get("X-User-Id")

		key := fmt.Sprintf("user_id:%s:date_time:%s", userID, timeNow)

		count, err := c.redisClient.Incr(ctx, key).Result()
		if err != nil {
			log.Printf("coudn't increment limit for key: %s", key)
			w.WriteHeader(http.StatusInternalServerError)

			return
		}

		if count > limit {
			log.Printf("too many requests for key: %s", key)
			w.WriteHeader(http.StatusTooManyRequests)

			return
		}

		if count == 1 {
			log.Printf("set expire for key: %s", key)

			c.redisClient.Expire(ctx, key, 1*time.Minute)
		}

		next.ServeHTTP(w, r)
	})
}

type handlerClient struct {
	redisClient *redis.Client
}

func newHandlerClient() *handlerClient {
	rdb := redis.NewClient(&redis.Options{
		Addr:     "localhost:6379",
		Password: "", // no password set
		DB:       0,  // use default DB
	})

	return &handlerClient{
		redisClient: rdb,
	}
}

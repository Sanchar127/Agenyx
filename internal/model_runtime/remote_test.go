package model_runtime

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRemoteClientEmbed(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Errorf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/embed" {
			t.Errorf("expected /embed, got %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"embedding": []float64{0.1, 0.2, 0.3},
		})
	}))
	defer server.Close()

	client := NewRemoteClient(server.URL, "", 0)
	vec, err := client.Embed(context.Background(), "hello")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(vec) != 3 || vec[0] != 0.1 || vec[1] != 0.2 || vec[2] != 0.3 {
		t.Errorf("unexpected embedding: %v", vec)
	}
}

func TestRemoteClientEmbedDataWrapper(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"data": []interface{}{
				map[string]interface{}{
					"embedding": []float64{0.5, 0.5},
				},
			},
		})
	}))
	defer server.Close()

	client := NewRemoteClient(server.URL, "", 0)
	vec, err := client.Embed(context.Background(), "hello")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(vec) != 2 || vec[0] != 0.5 || vec[1] != 0.5 {
		t.Errorf("unexpected embedding: %v", vec)
	}
}

func TestRemoteClientAPIKey(t *testing.T) {
	var gotAuth string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"embedding": []float64{0.1},
		})
	}))
	defer server.Close()

	client := NewRemoteClient(server.URL, "secret-key", 0)
	if _, err := client.Embed(context.Background(), "x"); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if gotAuth != "Bearer secret-key" {
		t.Errorf("expected Authorization Bearer secret-key, got %q", gotAuth)
	}
}

func TestRemoteClientServerError(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "internal error", http.StatusInternalServerError)
	}))
	defer server.Close()

	client := NewRemoteClient(server.URL, "", 0)
	_, err := client.Embed(context.Background(), "x")
	if err == nil {
		t.Fatal("expected error for server error response")
	}
	if !strings.Contains(err.Error(), "status 500") {
		t.Errorf("expected status 500 in error, got %v", err)
	}
}

func TestRemoteClientTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// respond slowly so the client-side timeout fires first
		<-time.After(5 * time.Second)
	}))
	defer server.CloseClientConnections()

	client := NewRemoteClient(server.URL, "", 50*time.Millisecond)
	_, err := client.Embed(context.Background(), "x")
	if err == nil {
		t.Fatal("expected error for timeout")
	}
}

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
)

type executeRequest struct {
	Tool      string         `json:"tool"`
	Arguments map[string]any `json:"arguments"`
}

type executeResponse struct {
	Ok    bool   `json:"ok"`
	Result string `json:"result,omitempty"`
	Error  string `json:"error,omitempty"`
}

func executeHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req executeRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON request", http.StatusBadRequest)
		return
	}

	log.Printf("sandbox_execute tool=%s arguments=%v", req.Tool, req.Arguments)

	// Minimal stub: echo back a simple result for any tool call.
	result := fmt.Sprintf("Sandbox executed tool %q with arguments %v", req.Tool, req.Arguments)

	resp := executeResponse{
		Ok:     true,
		Result: result,
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(resp)
}

func main() {
	addr := os.Getenv("SANDBOX_ADDR")
	if addr == "" {
		addr = ":9000"
	}

	http.HandleFunc("/execute", executeHandler)

	log.Printf("sandbox listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatalf("sandbox server failed: %v", err)
	}
}

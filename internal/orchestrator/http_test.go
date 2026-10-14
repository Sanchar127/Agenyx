package orchestrator

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHTTPRun(t *testing.T) {
	queue := &fakeQueue{}
	handler := HTTPHandler(NewService(queue))

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/agent/run",
		strings.NewReader(`{"intent":"summarize this report"}`),
	)
	req.Header.Set("Content-Type", "application/json")

	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusAccepted {
		t.Fatalf("status = %d, want %d; body = %s",
			rec.Code, http.StatusAccepted, rec.Body.String())
	}

	var result RunResult
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode response: %v", err)
	}

	if result.ExecutionID == "" {
		t.Fatal("expected execution ID")
	}
	if result.Status != "queued" {
		t.Fatalf("status = %q, want queued", result.Status)
	}
	if queue.submittedIntent != "summarize this report" {
		t.Fatalf("submitted intent = %q", queue.submittedIntent)
	}
}

func TestHTTPRunRejectsEmptyIntent(t *testing.T) {
	handler := HTTPHandler(NewService(&fakeQueue{}))

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/agent/run",
		strings.NewReader(`{"intent":"   "}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusUnprocessableEntity {
		t.Fatalf("status = %d, want %d",
			rec.Code, http.StatusUnprocessableEntity)
	}
}

func TestHTTPRunQueueFailure(t *testing.T) {
	queue := &fakeQueue{
		submitErr: errors.New("connection refused"),
	}
	handler := HTTPHandler(NewService(queue))

	req := httptest.NewRequest(
		http.MethodPost,
		"/v1/agent/run",
		strings.NewReader(`{"intent":"do work"}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d",
			rec.Code, http.StatusServiceUnavailable)
	}
}

func TestHTTPGetExecution(t *testing.T) {
	queue := &fakeQueue{
		state: map[string]string{
			"execution_id": "test-id",
			"status":       "completed",
		},
	}
	handler := HTTPHandler(NewService(queue))

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/agent/runs/test-id",
		nil,
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want %d; body = %s",
			rec.Code, http.StatusOK, rec.Body.String())
	}

	var state map[string]string
	if err := json.Unmarshal(rec.Body.Bytes(), &state); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if state["status"] != "completed" {
		t.Fatalf("status = %q, want completed", state["status"])
	}
}

func TestHTTPGetExecutionNotFound(t *testing.T) {
	handler := HTTPHandler(NewService(&fakeQueue{
		state: map[string]string{},
	}))

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/agent/runs/missing-id",
		nil,
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want %d",
			rec.Code, http.StatusNotFound)
	}
}

func TestHTTPGetExecutionQueueFailure(t *testing.T) {
	handler := HTTPHandler(NewService(&fakeQueue{
		getErr: errors.New("connection refused"),
	}))

	req := httptest.NewRequest(
		http.MethodGet,
		"/v1/agent/runs/test-id",
		nil,
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusServiceUnavailable {
		t.Fatalf("status = %d, want %d",
			rec.Code, http.StatusServiceUnavailable)
	}
}

// Compile-time check that test helpers use the expected context API.
var _ = context.Background

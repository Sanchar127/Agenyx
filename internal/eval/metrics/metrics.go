package evalmetrics

import (
	"github.com/prometheus/client_golang/prometheus"
)

var (
	// Evaluation request metrics
	EvalRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "evaluation_requests_total",
			Help: "Total number of evaluation API requests",
		},
		[]string{"method", "endpoint", "status_code"},
	)

	EvalRequestsDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "evaluation_requests_duration_seconds",
			Help:    "Evaluation request duration in seconds",
			Buckets: prometheus.ExponentialBuckets(0.001, 2, 10),
		},
		[]string{"method", "endpoint"},
	)

	// Evaluation job metrics
	EvalJobsCreated = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "evaluation_jobs_created_total",
			Help: "Total number of evaluation jobs created",
		},
		[]string{"evaluation_type"},
	)

	EvalJobsCompleted = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "evaluation_jobs_completed_total",
			Help: "Total number of evaluation jobs completed",
		},
		[]string{"evaluation_type", "status"},
	)

	EvalJobDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "evaluation_job_duration_seconds",
			Help:    "Evaluation job duration in seconds",
			Buckets: prometheus.ExponentialBuckets(1, 2, 10),
		},
		[]string{"evaluation_type"},
	)

	// Worker metrics
	EvalWorkersTotal = prometheus.NewGaugeVec(
		prometheus.GaugeOpts{
			Name: "evaluation_workers_total",
			Help: "Total number of evaluation workers",
		},
		[]string{"worker_type", "status"},
	)

	// Comparison metrics
	EvalComparisonsCreated = prometheus.NewCounter(
		prometheus.CounterOpts{
			Name: "evaluation_comparisons_created_total",
			Help: "Total number of evaluation comparisons created",
		},
	)

	// RAG metrics (for RAG evaluation-specific metrics)
	EvalRAGRequestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "evaluation_rag_requests_total",
			Help: "Total number of RAG evaluation requests",
		},
		[]string{"endpoint", "status"},
	)

	EvalRAGChunksRetrieved = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "evaluation_rag_chunks_retrieved",
			Help:    "Number of chunks retrieved per RAG request",
			Buckets: prometheus.ExponentialBuckets(1, 2, 10),
		},
		[]string{"endpoint"},
	)

	EvalRAGContextChars = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "evaluation_rag_context_chars",
			Help:    "Number of context characters injected per RAG request",
			Buckets: prometheus.ExponentialBuckets(100, 2, 10),
		},
		[]string{"endpoint"},
	)
)

func init() {
	prometheus.MustRegister(
		EvalRequestsTotal,
		EvalRequestsDuration,
		EvalJobsCreated,
		EvalJobsCompleted,
		EvalJobDuration,
		EvalWorkersTotal,
		EvalComparisonsCreated,
		EvalRAGRequestsTotal,
		EvalRAGChunksRetrieved,
		EvalRAGContextChars,
	)
}

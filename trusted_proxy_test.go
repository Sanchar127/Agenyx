package main

import (
	"net/http/httptest"
	"net/netip"
	"reflect"
	"testing"
)

func mustParseTrustedProxies(t *testing.T, raw string) []netip.Prefix {
	t.Helper()

	prefixes, err := parseTrustedProxies(raw)
	if err != nil {
		t.Fatalf("parseTrustedProxies(%q): %v", raw, err)
	}

	return prefixes
}

func TestParseTrustedProxies(t *testing.T) {
	tests := []struct {
		name    string
		raw     string
		wantLen int
		wantErr bool
	}{
		{
			name:    "empty means no trusted proxies",
			raw:     "",
			wantLen: 0,
		},
		{
			name:    "single IPv4 address",
			raw:     "192.0.2.10",
			wantLen: 1,
		},
		{
			name:    "IPv4 and CIDR",
			raw:     "192.0.2.10, 10.0.0.0/8",
			wantLen: 2,
		},
		{
			name:    "IPv6 address",
			raw:     "2001:db8::1",
			wantLen: 1,
		},
		{
			name:    "invalid address",
			raw:     "not-an-ip",
			wantErr: true,
		},
		{
			name:    "empty entry",
			raw:     "192.0.2.10, ,10.0.0.0/8",
			wantErr: true,
		},
		{
			name:    "invalid CIDR",
			raw:     "192.0.2.0/99",
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := parseTrustedProxies(tt.raw)

			if tt.wantErr {
				if err == nil {
					t.Fatal("expected an error")
				}
				return
			}

			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if len(got) != tt.wantLen {
				t.Fatalf("got %d prefixes, want %d", len(got), tt.wantLen)
			}
		})
	}
}

func TestResolvedClientIP(t *testing.T) {
	tests := []struct {
		name       string
		remoteAddr string
		forwarded  string
		trusted    string
		want       string
	}{
		{
			name:       "direct client cannot spoof forwarded IP",
			remoteAddr: "198.51.100.10:1234",
			forwarded:  "203.0.113.99",
			trusted:    "10.0.0.0/8",
			want:       "198.51.100.10",
		},
		{
			name:       "no trusted proxies ignores forwarded IP",
			remoteAddr: "198.51.100.10:1234",
			forwarded:  "203.0.113.99",
			trusted:    "",
			want:       "198.51.100.10",
		},
		{
			name:       "trusted proxy forwards client IP",
			remoteAddr: "10.0.0.1:8080",
			forwarded:  "198.51.100.20",
			trusted:    "10.0.0.0/8",
			want:       "198.51.100.20",
		},
		{
			name:       "trusted proxy chain resolves right to left",
			remoteAddr: "10.0.0.1:8080",
			forwarded:  "198.51.100.20, 10.0.0.2",
			trusted:    "10.0.0.0/8",
			want:       "198.51.100.20",
		},
		{
			name:       "malformed forwarded chain falls back to immediate peer",
			remoteAddr: "10.0.0.1:8080",
			forwarded:  "198.51.100.20, invalid-ip",
			trusted:    "10.0.0.0/8",
			want:       "10.0.0.1",
		},
		{
			name:       "trusted proxy without forwarded header",
			remoteAddr: "10.0.0.1:8080",
			forwarded:  "",
			trusted:    "10.0.0.0/8",
			want:       "10.0.0.1",
		},
		{
			name:       "IPv6 direct client",
			remoteAddr: "[2001:db8::10]:1234",
			forwarded:  "2001:db8::99",
			trusted:    "10.0.0.0/8",
			want:       "2001:db8::10",
		},
		{
			name:       "IPv6 trusted proxy forwards IPv4 client",
			remoteAddr: "[2001:db8::1]:8080",
			forwarded:  "198.51.100.20",
			trusted:    "2001:db8::/32",
			want:       "198.51.100.20",
		},
		{
			name:       "trusted proxy does not trust addresses outside its range",
			remoteAddr: "192.0.2.10:8080",
			forwarded:  "203.0.113.99",
			trusted:    "10.0.0.0/8",
			want:       "192.0.2.10",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			trusted := mustParseTrustedProxies(t, tt.trusted)

			req := httptest.NewRequest("GET", "http://example.test/", nil)
			req.RemoteAddr = tt.remoteAddr
			if tt.forwarded != "" {
				req.Header.Set("X-Forwarded-For", tt.forwarded)
			}

			if got := resolvedClientIP(req, trusted); got != tt.want {
				t.Fatalf("resolvedClientIP() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestIsTrustedProxy(t *testing.T) {
	trusted := mustParseTrustedProxies(t, "10.0.0.0/8, 2001:db8::/32")

	tests := []struct {
		address string
		want    bool
	}{
		{address: "10.1.2.3", want: true},
		{address: "192.0.2.1", want: false},
		{address: "2001:db8::1", want: true},
		{address: "2001:dead::1", want: false},
		{address: "invalid", want: false},
	}

	for _, tt := range tests {
		t.Run(tt.address, func(t *testing.T) {
			addr, err := netip.ParseAddr(tt.address)
			if err != nil && tt.want {
				t.Fatalf("test address is invalid: %v", err)
			}
			if err != nil {
				addr = netip.Addr{}
			}

			if got := isTrustedProxy(addr, trusted); got != tt.want {
				t.Fatalf("isTrustedProxy(%q) = %v, want %v", tt.address, got, tt.want)
			}
		})
	}
}

func TestParseTrustedProxiesDoesNotMutateExpectedAddresses(t *testing.T) {
	got := mustParseTrustedProxies(t, "10.0.0.0/8, 192.0.2.1")
	want := []netip.Prefix{
		netip.MustParsePrefix("10.0.0.0/8"),
		netip.MustParsePrefix("192.0.2.1/32"),
	}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("prefixes = %#v, want %#v", got, want)
	}
}

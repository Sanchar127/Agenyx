package gateway

import (
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"strings"
)

// parseTrustedProxies parses a comma-separated list of trusted proxy IPs
// and CIDR ranges. An empty value means no proxies are trusted.
func parseTrustedProxies(raw string) ([]netip.Prefix, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}

	var prefixes []netip.Prefix

	for _, entry := range strings.Split(raw, ",") {
		entry = strings.TrimSpace(entry)
		if entry == "" {
			return nil, errors.New("trusted proxy configuration contains an empty entry")
		}

		if addr, err := netip.ParseAddr(entry); err == nil {
			addr = addr.Unmap()
			prefixes = append(prefixes, netip.PrefixFrom(addr, addr.BitLen()))
			continue
		}

		prefix, err := netip.ParsePrefix(entry)
		if err != nil {
			return nil, fmt.Errorf("invalid trusted proxy %q: expected an IP address or CIDR range", entry)
		}

		prefixes = append(prefixes, prefix.Masked())
	}

	return prefixes, nil
}

func isTrustedProxy(addr netip.Addr, trusted []netip.Prefix) bool {
	if !addr.IsValid() {
		return false
	}

	addr = addr.Unmap()

	for _, prefix := range trusted {
		prefixAddr := prefix.Addr()

		if prefixAddr.Is4In6() {
			prefix = netip.PrefixFrom(prefixAddr.Unmap(), prefix.Bits()-96)
		}

		if prefix.Contains(addr) {
			return true
		}
	}

	return false
}

// resolvedClientIP trusts X-Forwarded-For only when the immediate peer
// belongs to the configured trusted proxy ranges.
//
// It walks the forwarding chain from right to left and returns the first
// untrusted address. Invalid forwarding chains fall back to the immediate
// peer instead of trusting malformed client-provided information.
func resolvedClientIP(r *http.Request, trusted []netip.Prefix) string {
	remoteHost, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return clientIP(r)
	}

	remoteAddr, err := netip.ParseAddr(remoteHost)
	if err != nil {
		return clientIP(r)
	}

	remoteAddr = remoteAddr.Unmap()

	if !isTrustedProxy(remoteAddr, trusted) {
		return remoteAddr.String()
	}

	rawForwardedFor := r.Header.Get("X-Forwarded-For")
	if strings.TrimSpace(rawForwardedFor) == "" {
		return remoteAddr.String()
	}

	var chain []netip.Addr

	for _, entry := range strings.Split(rawForwardedFor, ",") {
		entry = strings.TrimSpace(entry)

		addr, err := netip.ParseAddr(entry)
		if err != nil {
			return remoteAddr.String()
		}

		chain = append(chain, addr.Unmap())
	}

	for i := len(chain) - 1; i >= 0; i-- {
		candidate := chain[i]

		if !isTrustedProxy(remoteAddr, trusted) {
			return remoteAddr.String()
		}

		if !isTrustedProxy(candidate, trusted) {
			return candidate.String()
		}

		remoteAddr = candidate
	}

	return remoteAddr.String()
}

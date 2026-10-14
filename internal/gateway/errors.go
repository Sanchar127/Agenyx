package gateway

import "errors"

var errInvalidUpstreamScheme = errors.New("upstream URL must use HTTP or HTTPS")

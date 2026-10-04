package integration_test

import (
	"fmt"
	"os"

	"google.golang.org/grpc/resolver"
)

func init() {
	fmt.Fprintf(os.Stderr, "ENGINEER04_TEST_ONLY_RESOLVER before=%s after=passthrough\n", resolver.GetDefaultScheme())
	resolver.SetDefaultScheme("passthrough")
}

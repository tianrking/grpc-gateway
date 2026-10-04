#!/usr/bin/env bash
set +e
git config --global --add safe.directory /grpc-gateway
export PATH="/go/bin:$PATH"
go version > /evidence/go-version.txt
go env > /evidence/go-env.txt
cat .bazelversion > /evidence/requested-bazel-version.txt
cat .github/Dockerfile > /evidence/source-Dockerfile.txt
run() {
  name="$1"
  command="$2"
  printf '%s\n' "$command" > "/evidence/$name.command"
  bash -o pipefail -c "$command" > "/evidence/$name.stdout" 2> "/evidence/$name.stderr"
  echo "$?" > "/evidence/$name.exit"
  git status --porcelain=v1 --untracked-files=all > "/evidence/$name.source-status"
  git diff HEAD > "/evidence/$name.source-diff"
}
if [ "$QUALITY_GROUP" != bazel ]; then run install 'make install'; fi
for tool in buf oapi-codegen swagger protoc-gen-grpc-gateway protoc-gen-openapiv2 protoc-gen-openapiv3 buildifier bazel; do
  path="$(command -v "$tool")"
  if [ -n "$path" ]; then
    go version -m "$path" > "/evidence/tool-$tool.version" 2>&1
    sha256sum "$path" > "/evidence/tool-$tool.sha256"
  fi
done
case "$QUALITY_GROUP" in
generation)
  run clean 'make clean'
  run generate 'make generate'
  run tidy 'go mod tidy'
  run generated-diff "git add -N . && git diff --exit-code HEAD --diff-filter=d && git diff --exit-code HEAD --diff-filter=D -- . ':(glob,exclude)examples/internal/clients/**/BUILD.bazel'"
  # Preserve the actual generator result. This job never restores source.
  ;;
bazel)
  run bazel-version 'bazel version'
  run gazelle 'bazel run //:gazelle && git add -N . && git diff --exit-code HEAD'
  run repositories 'bazel run //:gazelle -- update-repos -from_file=go.mod -to_macro=repositories.bzl%go_repositories && git add -N . && git diff --exit-code HEAD'
  run buildifier 'bazel run //:buildifier && git add -N . && git diff --exit-code HEAD'
  run bazel-race 'bazel test --nocache_test_results --@io_bazel_rules_go//go/config:race //...'
  ;;
api-proto)
  run staticcheck 'go tool staticcheck ./...'
  run gorelease 'go tool gorelease -base=v2.31.0'
  run vet 'go vet ./...'
  run proto-build 'buf build'
  run proto-lint 'buf lint'
  run proto-format 'buf format -w && git add -N . && git diff --exit-code HEAD'
  run proto-breaking "buf breaking --path protoc-gen-openapiv2/ --against 'https://github.com/grpc-ecosystem/grpc-gateway.git#branch=main'"
  run format-list 'gofmt -l $(git ls-files "*.go")'
  run changed-format 'test -z "$(gofmt -l runtime/fieldmask.go)"; if [ -f runtime/fieldmask_empty_object_test.go ]; then test -z "$(gofmt -l runtime/fieldmask_empty_object_test.go)"; fi'
  ;;
*) echo 'Unknown quality group' >&2; exit 2;;
esac
if [ "$QUALITY_GROUP" = generation ]; then
  run final-diff 'git diff --exit-code HEAD'
else
  run final-diff 'git diff --exit-code HEAD && test -z "$(git status --porcelain=v1 --untracked-files=all)"'
fi
exit 0

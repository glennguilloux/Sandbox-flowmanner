# fake_bin — Stubbed Commands for FlowManner Bats Tests

These fake binaries intercept real system commands (ssh, curl, docker, timeout,
sudo, md5sum, date) so tests never touch the network or real Docker containers.

## How they work

Each stub logs every invocation to `${STUB_DIR}/<cmd>.log` and reads its
response from `${STUB_DIR}/<cmd>.resp` (a one-shot response file) or
`${STUB_DIR}/<cmd>.default` (a persistent default).

### Setting responses in tests

```bash
# In your Bats test, after create_all_stubs:

# curl — per-URL responses (URL slashes → underscores in filename)
set_curl_response "http://localhost:3000" "200" "<html>page</html>"
set_curl_response "http://localhost:3000/api/health" "200" '{"status":"ok"}'

# ssh — generic response
stub_response "ssh" "OK"   # returns "OK" to stdout
stub_exit_code "ssh" 255   # exits with 255

# docker — generic response
stub_exit_code "docker" 1  # exits with 1

# md5sum — per-file hashes (deterministic in production, stubbed here)
stub_default "md5sum" "abc123def  myfile.js"

# timeout — pass exit code
stub_exit_code "timeout" 124  # simulate timeout
```

### Directory layout

```
scripts/tests/
├── deploy_flowmanner.bats   # test suite
├── helpers.bash             # stubs, mocks, assertions
├── run_tests.sh             # test runner
└── fixtures/
    └── fake_bin/            # this directory — populated at runtime
        └── README.md
```

### Adding new stubs

1. Create the stub script in helpers.bash `create_fake_<cmd>()` function
2. Call it from `create_all_stubs()`
3. Use `${STUB_DIR}/<cmd>.resp` for one-shot responses
4. Use `${STUB_DIR}/<cmd>.default` for persistent defaults
5. Log all invocations to `${STUB_DIR}/<cmd>.log`

### Important: Never call real network or real Docker

All commands under test (ssh, curl, docker, etc.) are replaced by these stubs
via PATH override. If a test accidentally calls the real binary, it will hit
production infrastructure. The `create_all_stubs()` function ensures every
required command is shadowed.

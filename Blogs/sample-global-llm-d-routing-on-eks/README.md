# Global llm-d routing for throughput

This repo holds the code from our blog post on routing LLM traffic across GPU clusters with llm-d.
A hub llm-d router in one cluster sends each request to the best leaf cluster. The leaf's own llm-d router
then picks the pod. The hub ranks clusters by the inter-token latency (ITL) a new request should expect.
It fills the fastest cluster up to its batch limit, then spills to the next one.

Only our own code is here. The plugin is a small addition to upstream
[llm-d-router](https://github.com/llm-d/llm-d-router) v0.11.0. The build script fetches upstream and adds
the plugin.

## What's in it

| Path | What it is |
|---|---|
| `llm-d-router-plugin/` | The `cluster-itl-scorer` EPP plugin (Go) and a patch that registers it |
| `registry/publisher.py` | Runs on each leaf. Writes the leaf's ITL and load to Valkey every 2 s |
| `registry/registrar.py` | Runs on the hub. Turns the Valkey records into the hub's cluster list |
| `deploy/` | Helm values and manifests for the hub, the leaves and the registry |
| `build/` | CodeBuild script that builds and pushes the EPP image |
| `infra/` | eksctl cluster configs and Transit Gateway scripts for our test bed |
| `loadgen/` | Streaming load generator, test scripts and result summaries |
| `bin/k` | Small kubectl wrapper the scripts use |

## How it works

1. Each leaf runs the llm-d router behind an internal NLB on ports 80 (traffic) and 9090 (metrics).
2. A publisher on each leaf reads the leaf's EPP and model server metrics. It fits
   ITL = a + b × running requests per pod, and writes a record to `llmd:cluster:<name>` in Valkey with a
   10 s expiry. It deletes the key on clean shutdown.
3. The registrar on the hub writes the live clusters into the `mc-hub-clusters` ConfigMap. The hub's
   `multicluster-file-discovery` plugin reads it.
4. The hub EPP runs `cluster-itl-scorer`. As a filter, it drops clusters with no fresh record or a failed
   health probe. As a scorer, it ranks clusters by expected ITL at the load after this request. It counts
   that load from the hub's own live in-flight count.

## The plugin

Files go in `pkg/epp/framework/plugins/scheduling/scorer/clusteritl/` of llm-d-router.
`runner.go.patch` adds two lines to `cmd/epp/runner/runner.go`, one import and one `Register` call.
The Redis client and the test Redis are already in upstream `go.mod`.

To build it by hand:

```bash
git clone --depth 1 --branch v0.11.0 https://github.com/llm-d/llm-d-router.git
cp -R llm-d-router-plugin/pkg/. llm-d-router/pkg/
git -C llm-d-router apply "$PWD/llm-d-router-plugin/runner.go.patch"
cd llm-d-router
go test ./pkg/epp/framework/plugins/scheduling/scorer/clusteritl/...
docker build -f Dockerfile.epp --build-arg TARGETOS=linux --build-arg TARGETARCH=amd64 -t <your-image> .
```

Or run `build/build-epp.sh <tag>`. It does the same in CodeBuild and pushes to ECR.

Plugin parameters:

| Parameter | Default | Meaning |
|---|---|---|
| `redisAddr` | required | Valkey or Redis `host:port` |
| `redisTLS` | `false` | Use TLS to Valkey |
| `keyPrefix` | `llmd:cluster:` | Key prefix the publishers write |
| `mode` | `predicted` | `predicted` uses the fitted line and hub in-flight. `best-pod` uses the best pod's ITL |
| `queuePenalty` | `1` | Cost multiplier past the batch limit. `10` gives spill behavior. `0` turns it off |
| `refreshInterval` | `500ms` | How often to read Valkey |
| `staleAfter` | `10s` | A record older than this is filtered out |
| `healthInterval` | off | How often to probe each cluster's metrics address, for example `1s` |
| `healthFailures` | `2` | Failed probes before a cluster is filtered out |

## Setup

You need EKS clusters that can reach each other's internal NLBs, a Valkey or Redis that every cluster can
reach, and an ECR repository.

1. Copy `env.example.sh` to `env.sh` and fill it in.
2. Create the clusters (`infra/eksctl/`) and connect their VPCs (`infra/tgw-attach.sh`,
   `infra/tgw-peer.sh`). Write their contexts to `infra/kubeconfig` with names `gr-hub`, `gr-leaf-*`.
3. Put `kubectl`, `helm` and `eksctl` in `bin/`. The scripts use these, not a global install.
4. Build the image with `build/build-epp.sh <tag>`, and set `EPP_TAG` to that tag.
5. Deploy each leaf with `deploy/deploy-leaf.sh <context>`. This runs the simulator. To use real vLLM on GPU
   nodes, run `deploy/swap-to-vllm.sh <context>`.
6. Start the registry with `deploy/deploy-registry.sh`.
7. Deploy the hub with `deploy/deploy-hub.sh itl-spill`. Other policies are `itl-predicted`,
   `itl-best-pod`, and the upstream `load` and `latency`.

Check the hub EPP log for `auto-created default producer` with `inflight-load-producer` and consumer `itl`.
That proves the plugin can see its own routing decisions.

## Testing

- `loadgen/run.sh` runs one load test as a Job in the hub cluster. Set `CONCURRENCY`, `REQUESTS` or
  `DURATION`, `MAX_TOKENS` and `MODEL`. It prints one `RESULT` JSON line.
- `loadgen/matrix.sh` deploys each policy in `POLICIES`, warms it up, and runs each concurrency in `CONCS`.
- `loadgen/lifecycle.sh graceful|crash` stops a leaf under load.
- `loadgen/registry-outage.sh` reboots the Valkey node under load.
- `loadgen/summarize.py` and `loadgen/life_summary.py` turn results into tables.

## Known limits

- The hub's Envoy forwards to `ip:port` only, so the publisher registers its NLB's IP, not its name.
- Hub to leaf traffic is plain HTTP over the private network.
- No retries. A crashed leaf causes about 3 s of errors before the health probe removes it.
- The plugin is Alpha in llm-d terms. The EPP needs `--allow-experimental-plugins`, which `hub.values.yaml`
  sets.
- Use `apiVersion: llm-d.ai/v1alpha1` in EndpointPickerConfig with v0.11.0 images.
- `infra/eksctl/` holds our test bed's GPU node groups, including fallback groups for regions that were
  out of capacity. Treat them as examples.

## License

This sample is licensed under the MIT-0 License. See `LICENSE`.

Some files come from the llm-d projects, which use the Apache License 2.0. `THIRD-PARTY-LICENSES`
lists them, and each one carries an Apache-2.0 SPDX header. A built EPP image includes llm-d-router
code, so keep llm-d's license and notice files when you share the image.

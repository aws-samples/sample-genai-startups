// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

// Package clusteritl scores whole clusters (hub mode) by inter-token latency.
//
// Each leaf cluster runs a publisher that writes a JSON record to Redis/Valkey under
// <keyPrefix><cluster> with a short TTL. This plugin polls those records in the
// background and acts as both:
//   - a Filter that drops clusters whose record is missing or stale (fast deregistration,
//     independent of the clusters file reload), and
//   - a Scorer that ranks clusters by expected ITL for the next request.
//
// Modes:
//   - "best-pod":  cost = ITL of the cluster's best pod, as the leaf reports it.
//   - "predicted": cost = a + b*r, with a, b fitted by the leaf (ITL vs running requests per pod)
//     and r the per-pod load after this request, using the hub's own live in-flight count.
package clusteritl

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
	"sigs.k8s.io/controller-runtime/pkg/log"

	logutil "github.com/llm-d/llm-d-router/pkg/common/observability/logging"
	fwkplugin "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/plugin"
	fwksched "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/scheduling"
	attrconcurrency "github.com/llm-d/llm-d-router/pkg/epp/framework/plugins/datalayer/attribute/concurrency"
)

const (
	PluginType = "cluster-itl-scorer"

	ModeBestPod   = "best-pod"
	ModePredicted = "predicted"
)

var (
	_ fwksched.Scorer          = &Plugin{}
	_ fwksched.Filter          = &Plugin{}
	_ fwkplugin.ConsumerPlugin = &Plugin{}
)

// Record is what a leaf publisher writes for its cluster.
type Record struct {
	Cluster       string  `json:"cluster"`
	TS            float64 `json:"ts"`
	Ready         float64 `json:"ready"`
	MaxSeqs       float64 `json:"max_seqs"`
	ITLms         float64 `json:"itl_ms"`
	BestPodITLms  float64 `json:"best_pod_itl_ms"`
	RunningPerPod float64 `json:"running_per_pod"`
	Waiting       float64 `json:"waiting"`
	ITLAms        float64 `json:"itl_a_ms"`
	ITLBms        float64 `json:"itl_b_ms"`
	FitN          float64 `json:"fit_n"`
	Metrics       string  `json:"metrics"`
}

type Config struct {
	RedisAddr       string `json:"redisAddr"`
	RedisTLS        bool   `json:"redisTLS"`
	KeyPrefix       string `json:"keyPrefix"`
	Mode            string `json:"mode"`
	RefreshInterval string `json:"refreshInterval"`
	StaleAfter      string `json:"staleAfter"`
	// QueuePenalty scales cost once the per-pod load passes capacity, since extra requests
	// wait for a decode slot: cost *= 1 + QueuePenalty*(r-maxSeqs)/maxSeqs. At 1 this is the
	// per-token cost of waiting; larger values spill to other clusters before queueing. 0 disables.
	QueuePenalty float64 `json:"queuePenalty"`
	// HealthInterval enables a hub-side probe of each cluster's metrics address. After
	// HealthFailures consecutive failures the cluster is filtered out until a probe succeeds.
	// This covers the window in which a crashed cluster's record has not yet expired. "" disables.
	HealthInterval string `json:"healthInterval"`
	HealthFailures int    `json:"healthFailures"`
}

type Plugin struct {
	typedName    fwkplugin.TypedName
	cfg          Config
	staleAfter   time.Duration
	inFlightKey  fwkplugin.DataKey
	mu           sync.RWMutex
	records      map[string]Record
	lastRefreshT time.Time
	fails        map[string]int
}

func Factory(name string, raw *json.Decoder, handle fwkplugin.Handle) (fwkplugin.Plugin, error) {
	cfg := Config{KeyPrefix: "llmd:cluster:", Mode: ModePredicted, RefreshInterval: "500ms", StaleAfter: "10s", QueuePenalty: 1,
		HealthFailures: 2}
	if raw != nil {
		if err := raw.Decode(&cfg); err != nil {
			return nil, fmt.Errorf("%s: bad parameters: %w", PluginType, err)
		}
	}
	if cfg.RedisAddr == "" {
		return nil, fmt.Errorf("%s: redisAddr is required", PluginType)
	}
	if cfg.Mode != ModeBestPod && cfg.Mode != ModePredicted {
		return nil, fmt.Errorf("%s: mode must be %q or %q", PluginType, ModeBestPod, ModePredicted)
	}
	refresh, err := time.ParseDuration(cfg.RefreshInterval)
	if err != nil {
		return nil, fmt.Errorf("%s: refreshInterval: %w", PluginType, err)
	}
	stale, err := time.ParseDuration(cfg.StaleAfter)
	if err != nil {
		return nil, fmt.Errorf("%s: staleAfter: %w", PluginType, err)
	}
	p := &Plugin{
		typedName:   fwkplugin.TypedName{Type: PluginType, Name: name},
		cfg:         cfg,
		staleAfter:  stale,
		inFlightKey: attrconcurrency.InFlightLoadDataKey,
		records:     map[string]Record{},
		fails:       map[string]int{},
	}
	opts := &redis.Options{Addr: cfg.RedisAddr}
	if cfg.RedisTLS {
		opts.TLSConfig = &tls.Config{MinVersion: tls.VersionTLS12}
	}
	ctx := context.Background()
	if handle != nil && handle.Context() != nil {
		ctx = handle.Context()
	}
	go p.poll(ctx, redis.NewClient(opts), refresh)
	if cfg.HealthInterval != "" {
		every, err := time.ParseDuration(cfg.HealthInterval)
		if err != nil {
			return nil, fmt.Errorf("%s: healthInterval: %w", PluginType, err)
		}
		go p.probe(ctx, every)
	}
	return p, nil
}

func (p *Plugin) TypedName() fwkplugin.TypedName { return p.typedName }

func (p *Plugin) Category() fwksched.ScorerCategory { return fwksched.Distribution }

// Consumes requires the hub's live in-flight load per cluster. Only Required keys make the
// loader auto-create the default inflight-load-producer.
func (p *Plugin) Consumes() fwkplugin.DataDependencies {
	return fwkplugin.DataDependencies{
		Required: map[fwkplugin.DataKey]any{p.inFlightKey: attrconcurrency.InFlightLoad{}},
	}
}

func (p *Plugin) poll(ctx context.Context, rdb *redis.Client, every time.Duration) {
	logger := log.FromContext(ctx).WithName(PluginType)
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		if err := p.refresh(ctx, rdb); err != nil {
			logger.V(logutil.VERBOSE).Info("registry refresh failed; keeping last records", "err", err.Error())
		}
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
	}
}

func (p *Plugin) refresh(ctx context.Context, rdb *redis.Client) error {
	ctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	var keys []string
	iter := rdb.Scan(ctx, 0, p.cfg.KeyPrefix+"*", 100).Iterator()
	for iter.Next(ctx) {
		keys = append(keys, iter.Val())
	}
	if err := iter.Err(); err != nil {
		return err
	}
	recs := map[string]Record{}
	if len(keys) > 0 {
		vals, err := rdb.MGet(ctx, keys...).Result()
		if err != nil {
			return err
		}
		for i, v := range vals {
			s, ok := v.(string)
			if !ok {
				continue
			}
			var r Record
			if json.Unmarshal([]byte(s), &r) != nil {
				continue
			}
			if r.Cluster == "" {
				r.Cluster = strings.TrimPrefix(keys[i], p.cfg.KeyPrefix)
			}
			recs[r.Cluster] = r
		}
	}
	p.mu.Lock()
	p.records, p.lastRefreshT = recs, time.Now()
	p.mu.Unlock()
	return nil
}

func (p *Plugin) probe(ctx context.Context, every time.Duration) {
	client := &http.Client{Timeout: every / 2}
	t := time.NewTicker(every)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		p.mu.RLock()
		targets := make(map[string]string, len(p.records))
		for name, r := range p.records {
			if r.Metrics != "" {
				targets[name] = r.Metrics
			}
		}
		p.mu.RUnlock()
		var wg sync.WaitGroup
		results := make(map[string]bool, len(targets))
		var rmu sync.Mutex
		for name, addr := range targets {
			wg.Add(1)
			go func(name, addr string) {
				defer wg.Done()
				ok := false
				if resp, err := client.Get("http://" + addr + "/metrics"); err == nil {
					_ = resp.Body.Close()
					ok = resp.StatusCode < 500
				}
				rmu.Lock()
				results[name] = ok
				rmu.Unlock()
			}(name, addr)
		}
		wg.Wait()
		p.mu.Lock()
		for name, ok := range results {
			if ok {
				delete(p.fails, name)
			} else {
				p.fails[name]++
			}
		}
		p.mu.Unlock()
	}
}

// live returns the record for an endpoint if it is present and fresh.
func (p *Plugin) live(ep fwksched.Endpoint, now time.Time) (Record, bool) {
	md := ep.GetMetadata()
	if md == nil {
		return Record{}, false
	}
	p.mu.RLock()
	r, ok := p.records[md.Name]
	down := p.cfg.HealthFailures > 0 && p.fails[md.Name] >= p.cfg.HealthFailures
	p.mu.RUnlock()
	if !ok || down {
		return Record{}, false
	}
	age := now.Sub(time.Unix(0, int64(r.TS*float64(time.Second))))
	return r, age <= p.staleAfter
}

// Filter drops clusters with no fresh record. If none are fresh (registry outage), it keeps
// every candidate so routing degrades to the other scorers instead of stopping.
func (p *Plugin) Filter(_ context.Context, _ *fwksched.InferenceRequest, eps []fwksched.Endpoint) []fwksched.Endpoint {
	now := time.Now()
	out := make([]fwksched.Endpoint, 0, len(eps))
	for _, ep := range eps {
		if _, ok := p.live(ep, now); ok {
			out = append(out, ep)
		}
	}
	if len(out) == 0 {
		return eps
	}
	return out
}

func (p *Plugin) hubInFlight(ep fwksched.Endpoint) float64 {
	raw, ok := ep.Get(p.inFlightKey)
	if !ok {
		return 0
	}
	if l, ok := raw.(*attrconcurrency.InFlightLoad); ok && l != nil {
		return float64(l.Requests)
	}
	return 0
}

// cost is the expected ITL (ms) a new request would see on this cluster.
func (p *Plugin) cost(r Record, hubInFlight float64) float64 {
	if p.cfg.Mode == ModeBestPod {
		if r.BestPodITLms > 0 {
			return r.BestPodITLms
		}
		return r.ITLms
	}
	ready := math.Max(r.Ready, 1)
	// The leaf's view is up to one publish interval old; the hub's in-flight count is live.
	perPod := math.Max(r.RunningPerPod, hubInFlight/ready) + 1/ready
	a, b := r.ITLAms, r.ITLBms
	if r.FitN < 3 || a <= 0 {
		a, b = r.ITLms, 0 // no fit yet: fall back to the measured mean
	}
	c := a + b*math.Min(perPod, math.Max(r.MaxSeqs, 1))
	if p.cfg.QueuePenalty > 0 && r.MaxSeqs > 0 && perPod > r.MaxSeqs {
		c *= 1 + p.cfg.QueuePenalty*(perPod-r.MaxSeqs)/r.MaxSeqs
	}
	return c
}

func (p *Plugin) Score(ctx context.Context, _ *fwksched.InferenceRequest, eps []fwksched.Endpoint) map[fwksched.Endpoint]float64 {
	now := time.Now()
	costs := make(map[fwksched.Endpoint]float64, len(eps))
	minC, maxC := math.Inf(1), math.Inf(-1)
	for _, ep := range eps {
		r, ok := p.live(ep, now)
		if !ok || (r.ITLms <= 0 && r.BestPodITLms <= 0) {
			continue // unscored: no signal yet
		}
		c := p.cost(r, p.hubInFlight(ep))
		costs[ep] = c
		minC, maxC = math.Min(minC, c), math.Max(maxC, c)
	}
	scores := make(map[fwksched.Endpoint]float64, len(costs))
	for ep, c := range costs {
		if maxC == minC {
			scores[ep] = 1
		} else {
			scores[ep] = (maxC - c) / (maxC - minC)
		}
	}
	if v := log.FromContext(ctx).V(logutil.DEBUG); v.Enabled() {
		dbg := map[string]float64{}
		for ep, c := range costs {
			dbg[ep.GetMetadata().Name] = math.Round(c*100) / 100
		}
		v.Info("cluster-itl costs", "mode", p.cfg.Mode, "costMs", dbg)
	}
	return scores
}

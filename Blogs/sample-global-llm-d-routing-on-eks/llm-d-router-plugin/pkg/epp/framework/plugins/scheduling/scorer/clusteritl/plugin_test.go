// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

package clusteritl

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	fwkdl "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/datalayer"
	fwksched "github.com/llm-d/llm-d-router/pkg/epp/framework/interface/scheduling"
	attrconcurrency "github.com/llm-d/llm-d-router/pkg/epp/framework/plugins/datalayer/attribute/concurrency"
)

func newPlugin(t *testing.T, mode string) (*Plugin, *miniredis.Miniredis, *redis.Client) {
	t.Helper()
	mr := miniredis.RunT(t)
	raw := `{"redisAddr":"` + mr.Addr() + `","mode":"` + mode + `","refreshInterval":"1h"}`
	p, err := Factory("itl", json.NewDecoder(strings.NewReader(raw)), nil)
	require.NoError(t, err)
	return p.(*Plugin), mr, redis.NewClient(&redis.Options{Addr: mr.Addr()})
}

func put(t *testing.T, mr *miniredis.Miniredis, r Record) {
	t.Helper()
	if r.TS == 0 {
		r.TS = float64(time.Now().UnixNano()) / 1e9
	}
	b, _ := json.Marshal(r)
	require.NoError(t, mr.Set("llmd:cluster:"+r.Cluster, string(b)))
}

func ep(name string, inflight int64) fwksched.Endpoint {
	attr := fwkdl.NewAttributes()
	attr.Put(attrconcurrency.InFlightLoadDataKey, &attrconcurrency.InFlightLoad{Requests: inflight})
	return fwksched.NewEndpoint(&fwkdl.EndpointMetadata{Name: name}, nil, attr)
}

func TestFactoryValidation(t *testing.T) {
	_, err := Factory("x", json.NewDecoder(strings.NewReader(`{}`)), nil)
	assert.Error(t, err, "redisAddr required")
	_, err = Factory("x", json.NewDecoder(strings.NewReader(`{"redisAddr":"a:1","mode":"fastest"}`)), nil)
	assert.Error(t, err, "unknown mode")
}

func TestBestPodModeRanksByReportedITL(t *testing.T) {
	p, mr, rdb := newPlugin(t, ModeBestPod)
	put(t, mr, Record{Cluster: "fast", BestPodITLms: 15, ITLms: 30})
	put(t, mr, Record{Cluster: "slow", BestPodITLms: 40, ITLms: 41})
	require.NoError(t, p.refresh(context.Background(), rdb))

	fast, slow := ep("fast", 0), ep("slow", 0)
	s := p.Score(context.Background(), nil, []fwksched.Endpoint{fast, slow})
	assert.InDelta(t, 1.0, s[fast], 1e-9)
	assert.InDelta(t, 0.0, s[slow], 1e-9)
}

func TestPredictedModeUsesHubInFlight(t *testing.T) {
	p, mr, rdb := newPlugin(t, ModePredicted)
	// Same idle ITL; "a" degrades 2 ms per running request per pod, "b" 0.5 ms.
	put(t, mr, Record{Cluster: "a", Ready: 2, MaxSeqs: 16, ITLms: 15, ITLAms: 15, ITLBms: 2, FitN: 10})
	put(t, mr, Record{Cluster: "b", Ready: 2, MaxSeqs: 16, ITLms: 20, ITLAms: 20, ITLBms: 0.5, FitN: 10})
	require.NoError(t, p.refresh(context.Background(), rdb))

	// Idle: a is cheaper.
	a, b := ep("a", 0), ep("b", 0)
	s := p.Score(context.Background(), nil, []fwksched.Endpoint{a, b})
	assert.Greater(t, s[a], s[b])

	// Hub already has 20 requests on a (10 per pod): 15+2*10.5=36 vs b 20+0.5*0.5.
	a, b = ep("a", 20), ep("b", 0)
	s = p.Score(context.Background(), nil, []fwksched.Endpoint{a, b})
	assert.Greater(t, s[b], s[a])
}

func TestQueuePenaltyPastCapacity(t *testing.T) {
	p, _, _ := newPlugin(t, ModePredicted)
	r := Record{Ready: 1, MaxSeqs: 4, ITLms: 10, ITLAms: 10, ITLBms: 0, FitN: 10}
	assert.InDelta(t, 10.0, p.cost(r, 2), 1e-9)
	assert.InDelta(t, 20.0, p.cost(r, 7), 1e-9) // 8 per pod on 4 slots
	p.cfg.QueuePenalty = 10
	assert.InDelta(t, 110.0, p.cost(r, 7), 1e-9)
	p.cfg.QueuePenalty = 0
	assert.InDelta(t, 10.0, p.cost(r, 7), 1e-9)
}

func TestFilterDropsMissingAndStale(t *testing.T) {
	p, mr, rdb := newPlugin(t, ModePredicted)
	put(t, mr, Record{Cluster: "live", ITLms: 10})
	put(t, mr, Record{Cluster: "stale", ITLms: 10, TS: float64(time.Now().Add(-time.Minute).Unix())})
	require.NoError(t, p.refresh(context.Background(), rdb))

	live, stale, gone := ep("live", 0), ep("stale", 0), ep("gone", 0)
	got := p.Filter(context.Background(), nil, []fwksched.Endpoint{live, stale, gone})
	assert.Equal(t, []fwksched.Endpoint{live}, got)
}

func TestFilterFailsOpenWhenRegistryEmpty(t *testing.T) {
	p, _, rdb := newPlugin(t, ModePredicted)
	require.NoError(t, p.refresh(context.Background(), rdb))
	in := []fwksched.Endpoint{ep("a", 0), ep("b", 0)}
	assert.Equal(t, in, p.Filter(context.Background(), nil, in))
}

func TestConsumesRequiresInFlightLoad(t *testing.T) {
	p, _, _ := newPlugin(t, ModePredicted)
	_, ok := p.Consumes().Required[attrconcurrency.InFlightLoadDataKey]
	assert.True(t, ok, "in-flight load must be Required so its default producer is created")
}

func TestFilterDropsClusterFailingHealthProbe(t *testing.T) {
	p, mr, rdb := newPlugin(t, ModePredicted)
	put(t, mr, Record{Cluster: "up", ITLms: 10})
	put(t, mr, Record{Cluster: "down", ITLms: 10})
	require.NoError(t, p.refresh(context.Background(), rdb))
	p.fails["down"] = p.cfg.HealthFailures

	up, down := ep("up", 0), ep("down", 0)
	assert.Equal(t, []fwksched.Endpoint{up}, p.Filter(context.Background(), nil, []fwksched.Endpoint{up, down}))
}

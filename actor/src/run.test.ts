import assert from 'node:assert/strict';
import { once } from 'node:events';
import { createServer } from 'node:http';
import type { AddressInfo } from 'node:net';
import { test } from 'node:test';

import type { ClaimedQuery, ClaimResponse, JobsApi, SubmitResponse } from './api.js';
import { ApiError, HttpJobsApi } from './api.js';
import { fitForSubmit, MAX_JOBS_PER_SUBMIT, runOnce } from './run.js';
import { actorInput } from './scrape.js';

const OPTS = { maxQueries: 2, workerVersion: 'apify-actor/test' };

function query(slug: string): ClaimedQuery {
    return {
        dataset: `google_jobs:query:${slug}`, slug, query: `q ${slug}`,
        location: 'New York, NY', mode: 'nyc', date_chip: 'today',
    };
}

const OK: SubmitResponse = {
    accepted: 1, rejected: 0, dropped: 0, new: 1, updated: 0, unchanged: 0, watermark_advanced: true,
};

class FakeApi implements JobsApi {
    calls: string[] = [];
    submitted: Record<string, unknown[]> = {};
    released: string[] = [];

    constructor(
        private readonly claimResult: ClaimResponse | Error,
        private readonly submitError?: Error,
    ) {}

    async claim(body: { max: number; worker_version: string }): Promise<ClaimResponse> {
        this.calls.push(`claim max=${body.max} v=${body.worker_version}`);
        if (this.claimResult instanceof Error) throw this.claimResult;
        return this.claimResult;
    }

    async submit(dataset: string, jobs: unknown[]): Promise<SubmitResponse> {
        this.calls.push(`submit ${dataset}`);
        if (this.submitError) throw this.submitError;
        this.submitted[dataset] = jobs;
        return { ...OK, accepted: jobs.length };
    }

    async release(dataset: string): Promise<void> {
        this.calls.push(`release ${dataset}`);
        this.released.push(dataset);
    }
}

test('claims, scrapes and submits each query once', async () => {
    const api = new FakeApi({ queries: [query('a'), query('b')] });
    const summary = await runOnce(api, async (q) => [{ title: q.slug }], OPTS);
    assert.deepEqual(api.calls, [
        'claim max=2 v=apify-actor/test',
        'submit google_jobs:query:a',
        'submit google_jobs:query:b',
    ]);
    assert.deepEqual(api.submitted['google_jobs:query:a'], [{ title: 'a' }]);
    assert.equal(summary.failed, false);
    assert.equal(summary.outcomes.length, 2);
});

test('a failed scrape releases that claim and the next query still runs', async () => {
    const api = new FakeApi({ queries: [query('a'), query('b')] });
    const summary = await runOnce(api, async (q) => {
        if (q.slug === 'a') throw new Error('actor run ended FAILED');
        return [{ title: 'b' }];
    }, OPTS);
    assert.deepEqual(api.released, ['google_jobs:query:a']);
    assert.deepEqual(Object.keys(api.submitted), ['google_jobs:query:b']);
    assert.equal(summary.outcomes[0]?.status, 'scrape_failed');
    assert.equal(summary.failed, false, 'one query succeeded, so the run is not a failure');
});

test('every query failing marks the run failed', async () => {
    const api = new FakeApi({ queries: [query('a')] });
    const summary = await runOnce(api, async () => { throw new Error('boom'); }, OPTS);
    assert.equal(summary.failed, true);
});

test('a submit rejected by the server is recorded, not thrown', async () => {
    const api = new FakeApi({ queries: [query('a')] }, new ApiError(409, 'claim not held'));
    const summary = await runOnce(api, async () => [{}], OPTS);
    assert.equal(summary.outcomes[0]?.status, 'submit_failed');
    assert.match(summary.outcomes[0]?.error ?? '', /409/);
    assert.equal(summary.failed, true);
});

test('an empty result is still submitted, so the server releases the claim', async () => {
    const api = new FakeApi({ queries: [query('a')] });
    await runOnce(api, async () => [], OPTS);
    assert.deepEqual(api.submitted['google_jobs:query:a'], []);
});

test('paused: nothing is scraped and the run is green', async () => {
    let scraped = false;
    const api = new FakeApi({ paused: true, queries: [] });
    const summary = await runOnce(api, async () => { scraped = true; return []; }, OPTS);
    assert.equal(summary.idle, 'paused');
    assert.equal(summary.failed, false);
    assert.equal(scraped, false);
});

test('reserve reached and nothing stale are both green and idle', async () => {
    assert.equal((await runOnce(new FakeApi({ reserve_reached: true }), async () => [], OPTS)).idle,
        'reserve_reached');
    const idle = await runOnce(new FakeApi({ queries: [] }), async () => [], OPTS);
    assert.equal(idle.idle, 'nothing_stale');
    assert.equal(idle.failed, false);
});

test('the daily cap (429) is green; any other claim error throws', async () => {
    const capped = await runOnce(new FakeApi(new ApiError(429, 'daily limit reached (50/50)')), async () => [], OPTS);
    assert.equal(capped.idle, 'daily_cap');
    assert.equal(capped.failed, false);
    await assert.rejects(runOnce(new FakeApi(new ApiError(401, 'invalid API key')), async () => [], OPTS),
        (err: unknown) => err instanceof ApiError && err.status === 401);
});

test('fitForSubmit keeps one submit within the server limits', () => {
    const many = Array.from({ length: 80 }, (_, i) => ({ i }));
    assert.equal(fitForSubmit(many).length, MAX_JOBS_PER_SUBMIT);
    const big = Array.from({ length: 10 }, () => ({ description: 'x'.repeat(1000) }));
    const fitted = fitForSubmit(big, 5000);
    assert.ok(fitted.length > 0 && fitted.length < 10);
    assert.ok(Buffer.byteLength(JSON.stringify({ jobs: fitted })) <= 5000);
    assert.deepEqual(fitted, big.slice(0, fitted.length), 'trimmed from the end, order kept');
});

test('the nested actor input always pins num_results and max_pagination', () => {
    const input = actorInput(query('a'), 10);
    assert.equal(input.num_results, 10);
    assert.equal(input.max_pagination, 1);
    assert.equal(actorInput(query('a'), 25).max_pagination, 3);
    assert.equal(input.query, 'q a');
    assert.equal(input.location, 'New York, NY');
});

test('HttpJobsApi sends the bearer token, encodes the dataset and surfaces FastAPI detail', async () => {
    const seen: { url?: string; auth?: string; body?: string }[] = [];
    const server = createServer((req, res) => {
        let body = '';
        req.on('data', (c) => { body += c; });
        req.on('end', () => {
            seen.push({ url: req.url, auth: req.headers.authorization, body });
            if (req.url?.endsWith('/release')) {
                res.writeHead(409, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({ detail: 'claim not held' }));
                return;
            }
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(OK));
        });
    });
    server.listen(0, '127.0.0.1');
    await once(server, 'listening');
    const { port } = server.address() as AddressInfo;
    try {
        const api = new HttpJobsApi(`http://127.0.0.1:${port}/`, 'secret-token', 'test');
        const result = await api.submit('google_jobs:query:a b', [{ x: 1 }]);
        assert.equal(result.accepted, 1);
        assert.equal(seen[0]?.url, '/v1/queries/google_jobs%3Aquery%3Aa%20b/submit');
        assert.equal(seen[0]?.auth, 'Bearer secret-token');
        assert.deepEqual(JSON.parse(seen[0]?.body ?? ''), { jobs: [{ x: 1 }] });
        await assert.rejects(api.release('google_jobs:query:a', 'r'),
            (err: unknown) => err instanceof ApiError && err.status === 409 && err.detail === 'claim not held');
    } finally {
        server.close();
    }
});

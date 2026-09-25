/**
 * One run: claim -> scrape -> submit, against api/'s existing protocol
 * (backend/api/app.py `claim`, `submit`, `release`). docs/adr/0012.
 *
 * No Apify import here, and no network code, on purpose. main.ts wires the
 * real JobsApi and scrapeQuery in, and run.test.ts wires fakes, so every
 * branch below can be tested without an Apify account or a server.
 */

import type { ClaimedQuery, ClaimResponse, JobsApi, SubmitResponse } from './api.js';
import { ApiError } from './api.js';

/** api/app.py MAX_JOBS_PER_SUBMIT. The server refuses more with a 400. */
export const MAX_JOBS_PER_SUBMIT = 50;
/** api/app.py MAX_BODY_BYTES. The server refuses more with a 413 before parsing. */
export const MAX_BODY_BYTES = 2 * 1024 * 1024;

export type Scraper = (query: ClaimedQuery) => Promise<unknown[]>;

export interface RunOptions {
    maxQueries: number;
    workerVersion: string;
}

export interface QueryOutcome {
    slug: string;
    query: string;
    location: string;
    status: 'submitted' | 'scrape_failed' | 'submit_failed';
    scraped: number;
    submitted: number;
    result?: SubmitResponse;
    error?: string;
}

export interface RunSummary {
    /** Why the run did no work, when it did none. Absent when it claimed queries. */
    idle?: 'paused' | 'reserve_reached' | 'daily_cap' | 'nothing_stale';
    outcomes: QueryOutcome[];
    /** True when every claimed query failed, so the run should show as failed. */
    failed: boolean;
    message: string;
}

/**
 * Trim a result list to what one submit may carry.
 *
 * WHY NOT CHUNKING. A successful submit calls mark_success, which clears the
 * claim (api/query_claims.py). A second chunk against the same dataset would
 * find no claim and get a 409. So a query's results travel in exactly one
 * submit, trimmed from the end, where Google ranks the least relevant ones.
 * The input schema caps resultsPerQuery at MAX_JOBS_PER_SUBMIT, so trimming
 * by count only happens if the scraper returns more than it was asked for.
 */
export function fitForSubmit(jobs: unknown[], maxBytes = MAX_BODY_BYTES): unknown[] {
    let fitted = jobs.slice(0, MAX_JOBS_PER_SUBMIT);
    while (fitted.length > 0 && bodySize(fitted) > maxBytes) {
        fitted = fitted.slice(0, -1);
    }
    return fitted;
}

function bodySize(jobs: unknown[]): number {
    return Buffer.byteLength(JSON.stringify({ jobs }), 'utf8');
}

function describe(err: unknown): string {
    if (err instanceof ApiError) return `HTTP ${err.status}: ${err.detail}`;
    if (err instanceof Error) return err.message;
    return String(err);
}

export async function runOnce(api: JobsApi, scrape: Scraper, opts: RunOptions): Promise<RunSummary> {
    let claimed: ClaimResponse;
    try {
        claimed = await api.claim({ max: opts.maxQueries, worker_version: opts.workerVersion });
    } catch (err) {
        // 429 is the per-contributor daily cap (MAX_CLAIMS_PER_CONTRIBUTOR_PER_DAY).
        // It is a state the runner is correctly in, not a fault, so the run
        // ends green. A red run every day for a cap would train people to
        // ignore the one run that IS broken. Every other failure (401 bad
        // token, the server unreachable) propagates and fails the run.
        if (err instanceof ApiError && err.status === 429) {
            return {
                idle: 'daily_cap', outcomes: [], failed: false,
                message: `Daily limit reached on the server (${err.detail}). Nothing was scraped and nothing was spent.`,
            };
        }
        throw err;
    }

    if (claimed.paused) {
        return {
            idle: 'paused', outcomes: [], failed: false,
            message: 'Paused by the server operator. Nothing was scraped and nothing was spent. Keep the schedule; it resumes on its own.',
        };
    }
    if (claimed.reserve_reached) {
        return {
            idle: 'reserve_reached', outcomes: [], failed: false,
            message: 'The server granted no queries (reserve floor reached). Nothing was scraped and nothing was spent.',
        };
    }
    const queries = claimed.queries ?? [];
    if (queries.length === 0) {
        return {
            idle: 'nothing_stale', outcomes: [], failed: false,
            message: 'Nothing to do: every query was fetched recently. Nothing was scraped and nothing was spent.',
        };
    }

    const outcomes: QueryOutcome[] = [];
    for (const q of queries) {
        const base = { slug: q.slug, query: q.query, location: q.location };
        let jobs: unknown[];
        try {
            jobs = await scrape(q);
        } catch (err) {
            // Give the claim back now rather than leaving it to expire, so
            // another runner can take the query without waiting out the TTL.
            // A release that fails is not worth failing over: the claim
            // expires on its own.
            try {
                await api.release(q.dataset, describe(err).slice(0, 200));
            } catch {
                /* the claim expires on its own */
            }
            outcomes.push({ ...base, status: 'scrape_failed', scraped: 0, submitted: 0, error: describe(err) });
            continue;
        }

        const fitted = fitForSubmit(jobs);
        try {
            // An EMPTY list is still submitted. The server releases the claim
            // without advancing the watermark (defect D08), and that is the
            // correct record of "searched, found nothing".
            const result = await api.submit(q.dataset, fitted);
            outcomes.push({ ...base, status: 'submitted', scraped: jobs.length, submitted: fitted.length, result });
        } catch (err) {
            outcomes.push({ ...base, status: 'submit_failed', scraped: jobs.length, submitted: 0, error: describe(err) });
        }
    }

    const ok = outcomes.filter((o) => o.status === 'submitted').length;
    const failed = ok === 0;
    const accepted = outcomes.reduce((n, o) => n + (o.result?.accepted ?? 0), 0);
    return {
        outcomes,
        failed,
        message: `${ok}/${outcomes.length} queries submitted, ${accepted} postings accepted by the server.`,
    };
}

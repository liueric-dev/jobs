/**
 * The scrape step, delegated to a Google Jobs actor from the Apify Store.
 * docs/adr/0012 decision 2.
 *
 * WHY DELEGATED AND NOT OUR OWN SCRAPER. Apify's Google SERP proxy covers
 * Google Search and Shopping but not Google Jobs. Scraping Jobs directly means
 * a headless browser on residential proxies, which is the configuration a
 * cheaper third-party actor was already CAPTCHA-blocked in (the docstring of
 * backend/ingest/google-apify.py). This actor was chosen there for one more
 * reason: its output matches SerpApi's field for field, and that is the shape
 * the server's normalize_job reads.
 *
 * Replacing it means writing another Scraper (see run.ts) and changing
 * main.ts's wiring. The protocol and the server do not change.
 *
 * WHO PAYS. Actor.call runs the nested actor in the account that is running
 * THIS actor, so each classmate pays for their own results, per result.
 */

import { Actor } from 'apify';

import type { ClaimedQuery } from './api.js';
import type { Scraper } from './run.js';

export const GOOGLE_JOBS_ACTOR = 'johnvc/google-jobs-scraper---pay-per-result';

/** Mirrors ingest/google-apify.py's APIFY_RUN_TIMEOUT_SECS, with headroom. */
const NESTED_RUN_TIMEOUT_SECS = 240;

export function actorInput(query: ClaimedQuery, resultsPerQuery: number): Record<string, unknown> {
    return {
        query: query.query,
        location: query.location,
        country: 'us',
        // COST DISCIPLINE, from ingest/google-apify.py: ALWAYS set both.
        // Leaving them at the actor's defaults once cost $1.50 in a single call.
        num_results: resultsPerQuery,
        max_pagination: Math.max(1, Math.ceil(resultsPerQuery / 10)),
    };
}

export function googleJobsScraper(resultsPerQuery: number): Scraper {
    return async (query) => {
        const run = await Actor.call(GOOGLE_JOBS_ACTOR, actorInput(query, resultsPerQuery), {
            // A SECOND, platform-enforced cost ceiling behind num_results. On a
            // pay-per-result actor, Apify charges for at most this many items
            // whatever the input says.
            maxItems: resultsPerQuery,
            timeout: NESTED_RUN_TIMEOUT_SECS,
        });
        if (run.status !== 'SUCCEEDED') {
            throw new Error(`Google Jobs actor run ${run.id} ended ${run.status}`);
        }
        const { items } = await Actor.apifyClient
            .dataset(run.defaultDatasetId)
            .listItems({ clean: true, limit: resultsPerQuery });
        return items;
    };
}

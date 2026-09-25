/**
 * Entry point: read the input, run once, and report back to the classmate
 * who ran it. docs/adr/0012.
 */

import { Actor, log } from 'apify';

import { HttpJobsApi } from './api.js';
import { runOnce } from './run.js';
import { googleJobsScraper } from './scrape.js';

const VERSION = '0.1.0';
const WORKER_VERSION = `apify-actor/${VERSION}`;

interface Input {
    apiKey?: string;
    serverUrl?: string;
    maxQueries?: number;
    resultsPerQuery?: number;
}

await Actor.init();

const input = (await Actor.getInput<Input>()) ?? {};
const apiKey = (input.apiKey ?? '').trim();
if (!apiKey) {
    await Actor.fail(
        'No apiKey. Sign in to the jobs site with your Pursuit Google account, click '
        + '"Get actor token", and paste it into this actor\'s "Jobs API token" input.',
    );
}

const api = new HttpJobsApi(
    input.serverUrl ?? 'https://jobs-api.etotheric.com',
    apiKey,
    `${WORKER_VERSION} (+https://apify.com)`,
);
const scrape = googleJobsScraper(input.resultsPerQuery ?? 10);

try {
    const summary = await runOnce(api, scrape, {
        maxQueries: input.maxQueries ?? 1,
        workerVersion: WORKER_VERSION,
    });
    for (const outcome of summary.outcomes) {
        if (outcome.error) log.warning(`${outcome.slug}: ${outcome.status}: ${outcome.error}`);
        else log.info(`${outcome.slug}: submitted ${outcome.submitted} of ${outcome.scraped}`, { ...outcome.result });
    }
    // One dataset row per query, so the classmate can see in their own
    // console what their run contributed.
    if (summary.outcomes.length) await Actor.pushData(summary.outcomes.map((o) => ({ ...o })));

    if (summary.failed) await Actor.fail(summary.message);
    else await Actor.exit(summary.message);
} catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const hint = message.includes('HTTP 401')
        ? ' Your token was rejected. Get a new one from the jobs site; getting one revokes the old.'
        : '';
    await Actor.fail(`Jobs API request failed: ${message}.${hint}`);
}

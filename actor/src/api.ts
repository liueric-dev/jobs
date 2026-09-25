/**
 * The jobs API client: api/'s three contributor routes, over fetch.
 * Shapes mirror backend/api/app.py (ClaimRequest, SubmitRequest,
 * ReleaseRequest and the dicts `claim` / `submit` return).
 */

export interface ClaimedQuery {
    dataset: string;
    slug: string;
    query: string;
    location: string;
    mode: string;
    /** SerpApi's date filter. The delegated scraper has none, so it is ignored. */
    date_chip?: string | null;
}

export interface ClaimResponse {
    poll_interval_seconds?: number;
    paused?: boolean;
    reserve_reached?: boolean;
    queries?: ClaimedQuery[];
}

export interface SubmitResponse {
    accepted: number;
    rejected: number;
    dropped: number;
    new: number;
    updated: number;
    unchanged: number;
    watermark_advanced: boolean;
}

export interface JobsApi {
    claim(body: { max: number; worker_version: string }): Promise<ClaimResponse>;
    submit(dataset: string, jobs: unknown[]): Promise<SubmitResponse>;
    release(dataset: string, reason: string): Promise<void>;
}

export class ApiError extends Error {
    constructor(public readonly status: number, public readonly detail: string) {
        super(`jobs API returned HTTP ${status}: ${detail}`);
        this.name = 'ApiError';
    }
}

export class HttpJobsApi implements JobsApi {
    private readonly baseUrl: string;

    constructor(
        baseUrl: string,
        private readonly apiKey: string,
        private readonly userAgent: string,
        private readonly timeoutMs = 60_000,
    ) {
        this.baseUrl = baseUrl.replace(/\/+$/, '');
    }

    claim(body: { max: number; worker_version: string }): Promise<ClaimResponse> {
        return this.post('/v1/queries/claim', body) as Promise<ClaimResponse>;
    }

    submit(dataset: string, jobs: unknown[]): Promise<SubmitResponse> {
        return this.post(`/v1/queries/${encodeURIComponent(dataset)}/submit`, { jobs }) as Promise<SubmitResponse>;
    }

    async release(dataset: string, reason: string): Promise<void> {
        await this.post(`/v1/queries/${encodeURIComponent(dataset)}/release`, { reason });
    }

    private async post(path: string, body: unknown): Promise<unknown> {
        const response = await fetch(`${this.baseUrl}${path}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${this.apiKey}`,
                'User-Agent': this.userAgent,
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(this.timeoutMs),
        });
        const text = await response.text();
        if (!response.ok) {
            // FastAPI's error body is {"detail": ...}. The raw text is the
            // fallback, bounded because it lands in the run log.
            let detail = text.slice(0, 300);
            try {
                const parsed = JSON.parse(text) as { detail?: unknown };
                if (parsed.detail !== undefined) detail = String(parsed.detail).slice(0, 300);
            } catch {
                /* not JSON; keep the raw text */
            }
            throw new ApiError(response.status, detail);
        }
        return text ? JSON.parse(text) : {};
    }
}

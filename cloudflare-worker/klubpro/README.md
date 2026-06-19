# klubpro.com rebrand landing

KlubPro has been folded into Better Cricket. This Cloudflare Worker sits on the
old `klubpro.com` domain and serves one on-brand page telling visitors KlubPro
is now Better Cricket, with a call to action through to `betterat.cricket`.

Every path returns the same page (the domain is retired, so there is nothing
else to show) as a 200, not a redirect, so people read the announcement before
they click through. The page is self-contained: brand colours and fonts inline,
Open Graph card art pulled from the live site so a shared link still previews on
brand.

## Deploy

```bash
cd cloudflare-worker/klubpro
wrangler deploy
```

Then in the Cloudflare dashboard (klubpro.com zone) → Workers → Routes, confirm
the route `klubpro.com/*` points at the `klubpro-landing` worker. The route is
also declared in `wrangler.toml`, so a deploy from an account that holds the
klubpro.com zone sets it up.

## Editing the copy

The whole page is the `HTML` template string in `worker.js`. Change the headline
or call to action there and redeploy. Keep the plain cricket-club voice (run
prose through the `humanizer` skill, same as the rest of the site).

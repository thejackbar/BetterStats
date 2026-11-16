# Brief: launch the BetterCricket history video ad on Meta

**For:** a Claude session with access to Meta Ads Manager (browser or the Meta Ads tools) and to GitHub.
**Goal:** put the new 30-second video live as an ad in the existing trial campaign, tagged so BetterCricket can track it, archive three broken ads, and report back the new ad's ID.
**Ask the account owner before:** publishing anything, changing any budget, or deleting anything. Archiving the three broken ads (step 6) is approved.

## What you need

| Item | Value |
|---|---|
| Ad account | BetterCricket (ID `1030195476512456`) |
| Campaign | "November 2026 Trial Campaign" (ID `120251284365570121`) |
| Ad set | `AS_Trial_AU_Men3064_FBFeed` |
| Video file | `brag-output-2026-11-16-trial-ad/bettercricket-trial-ad-4x5.mp4` on GitHub repo `thejackbar/BetterStats`, branch `claude/trusting-bohr-kgf9iu` (30s, 1080x1350, 4:5, with sound) |
| Thumbnail | `brag-output-2026-11-16-trial-ad/poster.jpg`, same branch |
| New ad name | `Ad_Video_History_4x5_Nov2026` |
| Website URL | `https://betterat.cricket/trial` (exactly this, nothing after it) |
| URL parameters | `utm_source=meta&utm_medium=paid_social&utm_campaign=BC_AU_Trial_CBO_Sep2026&utm_content=history_video_4x5` |

## Steps

### 1. Download the video and thumbnail
On GitHub, open the repo `thejackbar/BetterStats`, switch to branch `claude/trusting-bohr-kgf9iu`, go to the folder `brag-output-2026-11-16-trial-ad/`, and download `bettercricket-trial-ad-4x5.mp4` and `poster.jpg` (open each file, then "Download raw file").

Check: the MP4 is about 10 MB, plays for 30 seconds, and starts with "Your club's whole history".

### 2. Open the ad set
Ads Manager, account "BetterCricket", campaign "November 2026 Trial Campaign", ad set `AS_Trial_AU_Men3064_FBFeed`. Do not change the campaign or ad set settings (budget, audience, placements, optimisation).

### 3. Create the new ad
In that ad set, create a new ad (not a duplicate of an old video ad).

- **Ad name:** `Ad_Video_History_4x5_Nov2026`
- **Identity:** the BetterCricket Facebook Page (the same one the live ad `Ad_CheckOutYourClub_v2_Relaunch` uses)
- **Format:** single image or video
- **Media:** upload `bettercricket-trial-ad-4x5.mp4` as a **video**. Do **not** choose an existing reel or Instagram post: the last three video ads broke because their reels were removed.
- **Thumbnail:** upload `poster.jpg` as the custom thumbnail
- **Primary text:**
  > Every season your club has played, synced automatically or added by hand. Drop in old spreadsheets, snap a photo of an old scorebook, and see who's next to a milestone. Find your club and start a free 14-day trial. No credit card.
- **Headline:** `Your club's whole history, in one place`
- **Description (if asked):** `Free 14-day trial · No credit card`
- **Call to action:** Sign up
- **Destination / Website URL:** `https://betterat.cricket/trial`
  - Nothing after `/trial`. No `?`, no `utm_` tags in this field.
- **Tracking section:**
  - Website events / pixel: leave as the ad set has it (dataset `1317878090534903`, the same as the live ad)
  - **URL parameters:** paste exactly
    `utm_source=meta&utm_medium=paid_social&utm_campaign=BC_AU_Trial_CBO_Sep2026&utm_content=history_video_4x5`

Why the URL rules matter: if tags are in both the website URL and URL parameters, the site reads the first one and the signup is credited to the wrong ad. Tags go only in URL parameters.

### 4. Check before publishing
- Preview the ad in Facebook Feed: the video plays with the green BetterCricket end card and "Start your free trial".
- Open "Preview link" or the ad's destination and confirm the final URL is
  `https://betterat.cricket/trial?utm_source=meta&utm_medium=paid_social&utm_campaign=BC_AU_Trial_CBO_Sep2026&utm_content=history_video_4x5`
  with no other `utm_` values in it.
- No errors or warnings in the ad editor.

### 5. Publish (confirm with the owner first)
Ask the owner for a yes, then publish. The ad goes to review; it usually clears within a day. Leave `Ad_CheckOutYourClub_v2_Relaunch` running alongside it.

### 6. Archive the three broken video ads
In the same ad set these show "Ad Creative Is Incomplete: the reel you selected for your ad is not available" and have had no delivery:

- `Ad_Video_V1_ClubRecords_1x1_Sep2026` (ID `120251460069150121`)
- `Ad_Video_V3_Availability_1x1_Sep2026` (ID `120251460370810121`)
- `Ad_Video_V5_MatchSocials_1x1_Sep2026` (ID `120251460370820121`)

Archive them (not delete). Do not touch any other ad.

## Report back (copy this, filled in)

```
New ad name: Ad_Video_History_4x5_Nov2026
New ad ID: <numeric id>
Creative ID: <numeric id>
Status: <in review / active / rejected + reason>
Final destination URL as Meta shows it: <url>
Archived: V1 <yes/no>, V3 <yes/no>, V5 <yes/no>
Anything that did not match this brief: <notes>
```

Give that to the BetterStats Claude session. It adds the new ad ID to `AD_DESTINATIONS` in `backend/app/services/meta_ads.py` and pushes to main, so the ad gets its own spend, signups and cost per trial row on Meta Ads HQ. Until then its signups still count for the campaign, but its spend shows as "(untagged)".

## If something goes wrong
- **Video won't upload or is rejected for size:** do not swap in another video or a reel. Stop and report.
- **Ad rejected in review:** report the exact reason. Do not edit and resubmit without asking.
- **The editor forces tags into the website URL:** stop and report; do not publish.

# BetterSocials Event Posts — handoff bundle

Branch-ready files for the BetterStats repo. I can read the repo but can't push
to GitHub from here, so this is packaged to drop straight in.

## Apply
```bash
git checkout -b feat/bettersocials-event-posts
# copy the frontend/ tree from this bundle over your repo root
cp -R frontend/ /path/to/BetterStats/frontend/
```
This adds:
- `frontend/src/social/event-templates.jsx`            (new)
- `frontend/src/components/admin/EventPostEditor.jsx`   (new)

Then make the edits in **EVENTS_INTEGRATION.md**:
- `frontend/src/pages/admin/AdminSocialPost.jsx` — 6 small edits + 2 render hooks
- `frontend/index.html` — 4 Google Font families

Open the PR using **PR_DESCRIPTION.md** as the body.

## Contents
- `frontend/…` — the two new source files at their final paths
- `EVENTS_INTEGRATION.md` — exact diffs for the two edited files
- `PR_DESCRIPTION.md` — ready-to-paste PR body

The standalone visual previews these were signed off from live in the project
root (`FloodlitPost.dc.html`, `GazettePost.dc.html`, … and `Event Post Suite.dc.html`)
if you want the reference renders.

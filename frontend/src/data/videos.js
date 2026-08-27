// Page copy for the /videos section.
//
// The VIDEOS THEMSELVES are no longer here — they live in the
// `instructional_videos` table and are managed by a Super Admin from the page
// itself (upload, retitle, replace the file, reorder, delete). Only the
// section's own standing introduction is checked in, since it is site copy
// rather than content anyone edits per video.
export const VIDEO_INTRO = {
  eyebrow: 'How-to walkthroughs',
  heading: 'Videos.',
  blurb:
    'Short walkthroughs of the jobs a club admin does in BetterCricket, recorded off the real screens. Watch one here, or download it and keep it on the laptop in the clubroom for whoever picks the job up next.',
}

// Shown in place of the grid when the library is empty. A visitor should get a
// sentence rather than a blank page, and a Super Admin should be told where
// the upload button is.
export const VIDEO_EMPTY = {
  visitor: 'There are no walkthroughs published yet. Check back shortly.',
  admin: 'No videos yet. Use “Add video” above to upload the first walkthrough.',
}

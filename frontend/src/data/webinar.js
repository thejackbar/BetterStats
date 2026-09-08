// The BetterCricket webinar — ONE date constant, and every before/after state
// derived from it.
//
// The brief that asked for this said it plainly: drive the pre/post-event
// behaviour from one exported constant, not from conditionals scattered across
// two pages. A promo block still advertising a webinar that happened last week
// is the failure nobody notices until a prospect does — so `/demo` and the
// `/trial` promo block both read `webinarState()` and nothing else.
//
// This mirrors `backend/app/services/webinar.py::EVENT`, hand-kept in step the
// same way `pricing.js` and `billing_pricing.py` are (there is no shared build
// step between the Vite frontend and FastAPI). The page renders its headline
// from THIS copy rather than waiting on a request, because the ad's traffic is
// mobile and a fetch in front of the H1 is a fetch in front of LCP; the server
// copy is the authority for the email, the calendar file and the recording
// link. The verification asserts the two agree rather than taking it on trust.

// 21 September 2026, 17:30 Perth. Perth is UTC+8 with no daylight saving, so
// that is 09:30 UTC — and the eastern states are still on AEST (UTC+10, DST
// starts in October), which is the 19:30 AEST on the ad creative. Both times
// on the page are the same instant.
export const WEBINAR = {
  key: 'webinar-2026-09-21',
  title: 'BetterCricket live demo + Q&A',
  startsAt: '2026-09-21T09:30:00Z',
  durationMinutes: 60,
  watchUrl: 'https://streamyard.com/watch/ibBKm5Ek4sQu',
  // The exact words the ad creative uses. Message match between the ad and the
  // top of the page is what stops paid traffic bouncing, so these are held as
  // strings rather than formatted from a timezone database at render time.
  dateLabel: 'Monday 21 September',
  timeLabel: '5:30pm AWST / 7:30pm AEST',
  // The short form, for the promo block on /trial where the line has to fit.
  shortLabel: 'Monday 21 September, 5:30pm AWST / 7:30pm AEST',
  recordedLabel: 'Recorded 21 September 2026',
}

export function webinarStart() {
  return new Date(WEBINAR.startsAt)
}

export function webinarEnd() {
  return new Date(webinarStart().getTime() + WEBINAR.durationMinutes * 60_000)
}

// Whether the session has finished. Deliberately the END of the hour, not the
// start: somebody arriving halfway through should still be sent to the live
// stream, not told to wait for a recording that does not exist yet.
export function isWebinarPast(now = new Date()) {
  return now >= webinarEnd()
}

// Everything either page needs to render, from the one constant.
//
// `isPast` is the SERVER's own answer (`GET /public/webinar`) and wins whenever
// it is given: the server's clock is right, and a visitor whose device clock is
// days out would otherwise be shown the wrong state entirely — offered a
// recording that does not exist yet, or sent to a stream that has finished.
// The local clock is the fallback, so the first paint is correct before the
// request lands rather than waiting on it.
//
// `recordingUrl` also comes from the server (a super admin pastes it into
// General Settings after the event). Until then a past event says the recording
// is coming rather than offering a link that goes nowhere.
export function webinarState({ now = new Date(), recordingUrl = null, isPast = null } = {}) {
  const past = typeof isPast === 'boolean' ? isPast : isWebinarPast(now)
  return {
    past,
    // What the button does, and what the success state hands over.
    watchUrl: past ? recordingUrl : WEBINAR.watchUrl,
    recordingPending: past && !recordingUrl,
    // Copy. Every string the two pages print in either state lives here, so a
    // wording change is one edit rather than a hunt through two components.
    heading: past ? 'Watch the BetterCricket demo' : 'See BetterCricket in action',
    subheading: 'The entire platform. Your questions answered.',
    whenLabel: past ? WEBINAR.recordedLabel : `${WEBINAR.dateLabel} · ${WEBINAR.timeLabel}`,
    submitLabel: past ? 'Get the recording' : 'Register now',
    submittingLabel: past ? 'Getting it…' : 'Registering…',
    // The /trial promo block.
    promoHeading: past ? 'Missed the live demo?' : 'Want a guided tour first?',
    promoBody: past
      ? 'Watch the recording: the whole platform, plus the questions clubs asked on the night.'
      : `Live demo and Q&A. ${WEBINAR.shortLabel}.`,
    promoCta: past ? 'Watch the demo recording' : 'Save your spot',
  }
}

// Google Calendar "add event" link, built here so the success state can offer
// it with no round trip. The .ics comes from the backend
// (/api/public/webinar/calendar.ics) rather than a browser-built blob, because
// that same URL is what the confirmation email links to.
export function googleCalendarUrl(watchUrl = WEBINAR.watchUrl) {
  const stamp = (d) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '')
  const params = new URLSearchParams({
    action: 'TEMPLATE',
    text: WEBINAR.title,
    dates: `${stamp(webinarStart())}/${stamp(webinarEnd())}`,
    details: `${WEBINAR.dateLabel} · ${WEBINAR.timeLabel}\n\nWatch here: ${watchUrl}`,
    location: watchUrl,
  })
  return `https://calendar.google.com/calendar/render?${params}`
}

export const WEBINAR_ICS_URL = '/api/public/webinar/calendar.ics'

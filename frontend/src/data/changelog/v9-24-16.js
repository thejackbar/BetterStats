export default {
  version: 'v9.24.16',
  date: '2026-08-16',
  sortKey: '2026-08-19T01:00:00Z',
  title: 'A restart no longer loses an email send, and a dead SES feed says so',
  items: [
    'Sending an email now records each batch of recipients as it goes, instead of writing every result at the very end. A restart part-way through used to lose the lot: the emails went out, but every recipient stayed "queued" and the campaign sat on 0 sent with no way to tell who had been reached.',
    'Because results are written as the send progresses, the recipient counts on an email now climb while it is sending rather than sitting on zero until it finishes.',
    'A campaign cut short by a restart is picked up and finished automatically when the server comes back. Recipients already handed to the email provider are marked unconfirmed and are never sent a second time — a duplicate to a real club is worse than a gap in our own records.',
    'The daily catch-up job now finds these campaigns too. It only ever looked for recipients held back by a daily send cap, so anything interrupted mid-send was never picked up by anything and stayed unfinished.',
    'An email cannot be dispatched twice at once, so the catch-up job can no longer double up on a send that is still running.',
    'The server now warns at startup when Amazon SES has stopped reporting deliveries and bounces back to us. Bounce and complaint suppression is built on that feed, so when it is disconnected nothing is ever suppressed — and every deliverability figure reads a perfect zero, which looks identical to everything being fine.',
    'The Sending limits card now shows whether that delivery feed is actually connected.',
  ],
}

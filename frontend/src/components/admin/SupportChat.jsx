import { useEffect } from 'react'
import { api } from '../../lib/api'
import { useAuth } from '../../contexts/AuthContext'

// The admin help window: Chatwoot's website widget, opened as the signed-in person.
// The server decides whether it exists (GET /club-admin/support-chat/identity returns
// { enabled: false } until Chatwoot is set up), so this draws nothing at all when it
// is off. Chatwoot owns the window, the conversation and the notifications to the team;
// the answers to simple questions come from the bot in routers/support_chat.py.
//
// The widget script is loaded once per page load and kept. Leaving /admin hides the
// launcher rather than tearing the widget down, and a different person signing in on
// the same browser resets it first so a chat never carries over to the next user.

let sdkPromise = null

function loadSdk(baseUrl, websiteToken) {
  if (sdkPromise) return sdkPromise
  sdkPromise = new Promise((resolve, reject) => {
    window.chatwootSettings = {
      position: 'right',
      type: 'expanded_bubble',
      launcherTitle: 'Help',
      darkMode: 'auto',
      locale: 'en',
    }
    const s = document.createElement('script')
    s.src = `${baseUrl}/packs/js/sdk.js`
    s.async = true
    s.onload = () => {
      try {
        window.chatwootSDK.run({ websiteToken, baseUrl })
        resolve()
      } catch (e) {
        reject(e)
      }
    }
    s.onerror = () => reject(new Error('The help window could not load'))
    document.head.appendChild(s)
  }).catch((e) => {
    sdkPromise = null // let a later visit try again
    throw e
  })
  return sdkPromise
}

function whenReady(fn) {
  if (window.$chatwoot && window.$chatwoot.hasLoaded) fn()
  else window.addEventListener('chatwoot:ready', fn, { once: true })
}

let lastIdentifier = null

export default function SupportChat() {
  const { user } = useAuth()
  const userId = user?.id
  const clubSlug = user?.club_slug

  useEffect(() => {
    if (!userId) return undefined
    let alive = true
    api.getSupportChatIdentity()
      .then((idn) => {
        if (!alive || !idn || !idn.enabled) return null
        return loadSdk(idn.base_url, idn.website_token).then(() => {
          if (!alive) return
          whenReady(() => {
            const cw = window.$chatwoot
            if (!cw) return
            if (lastIdentifier && lastIdentifier !== idn.identifier) cw.reset()
            lastIdentifier = idn.identifier
            const who = { identifier_hash: idn.identifier_hash }
            if (idn.name) who.name = idn.name
            if (idn.email) who.email = idn.email
            cw.setUser(idn.identifier, who)
            cw.setCustomAttributes(idn.attributes || {})
            cw.toggleBubbleVisibility('show')
          })
        })
      })
      .catch(() => {}) // the help window is optional, a failure here must not touch the page
    return () => {
      alive = false
      try {
        if (window.$chatwoot && window.$chatwoot.hasLoaded) window.$chatwoot.toggleBubbleVisibility('hide')
      } catch (e) { /* nothing to hide */ }
    }
    // clubSlug: a super admin acting as another club re-sends who and where they are.
  }, [userId, clubSlug])

  return null
}

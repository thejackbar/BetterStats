// A card asks for a smaller copy of a player's photo. sizedPhoto adds ?w= to the player photo routes and to nothing else.
//   node verification/verify_photo_sizes.mjs
import { sizedPhoto, CARD_HERO_W, CARD_HEAD_W } from '../src/lib/playerShots.js'

const PASS = [], FAIL = []
const check = (name, cond, detail = '') => { (cond ? PASS : FAIL).push(name); console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  -- ' + detail : ''}`) }

const hero = '/api/images/players/9c0dda58-0000-0000-0000-000000000001/hero-photo?v=ab12cd34'
check('a hero photo URL gets the size added after its version', sizedPhoto(hero, CARD_HERO_W) === `${hero}&w=${CARD_HERO_W}`)
check('the headshot and the action shot too', sizedPhoto('/api/images/players/x/photo?v=1', CARD_HEAD_W) === `/api/images/players/x/photo?v=1&w=${CARD_HEAD_W}` && sizedPhoto('/api/images/players/x/action-photo?v=1', 800) === '/api/images/players/x/action-photo?v=1&w=800')
check('a photo URL with no query gets ?w=', sizedPhoto('/api/images/players/x/photo', 480) === '/api/images/players/x/photo?w=480')
check('a size already on the URL is left alone', sizedPhoto(`${hero}&w=240`, 800) === `${hero}&w=240`)
check('a logo, a pack picture and another site are untouched', ['/api/images/organisations/o/logo', '/api/images/card-packs/d/bg?v=1', 'https://example.com/a.jpg', '/img/hero.jpg'].every((u) => sizedPhoto(u, 800) === u))
check('nothing in, nothing out', sizedPhoto(null, 800) === null && sizedPhoto(undefined, 800) === undefined && sizedPhoto('', 800) === '')
check('no size asked, no change', sizedPhoto(hero, 0) === hero && sizedPhoto(hero, undefined) === hero)
check('a longer route that only starts like a photo route is untouched', sizedPhoto('/api/images/players/x/photo-extra?v=1', 800) === '/api/images/players/x/photo-extra?v=1')
console.log(`\n${PASS.length} passed, ${FAIL.length} failed`)
if (FAIL.length) process.exit(1)

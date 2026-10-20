// The typeahead's matcher on its own: forgiving about spelling, word order and initials, and not
// so forgiving that it offers everyone.   node verify_fuzzy_match.mjs
import { suggest, norm } from '../src/lib/fuzzyMatch.js'
let pass = 0, fail = 0
const check = (name, cond, detail = '') => { cond ? pass++ : fail++; console.log(`${cond ? '  ok  ' : ' FAIL '} ${name}${!cond && detail ? '  — ' + detail : ''}`) }
const names = ['Ritchie, Peter', 'Ritchie, Rod', 'Hind, Darren', 'Smith, John', 'Smithson, Paul', 'Moore, Peter', 'Ball, Sam', 'Bell, Sam']
const got = (q, o) => suggest(names, q, o).shown
check('the right spelling finds the player', got('ritchie')[0].startsWith('Ritchie'))
check('a missing letter ("richie") still finds Ritchie', got('richie').join() === 'Ritchie, Rod,Ritchie, Peter' || got('richie').sort().join() === ['Ritchie, Peter', 'Ritchie, Rod'].join(), got('richie').join('|'))
check('a half-typed name finds it ("ritc")', got('ritc').length === 2)
check('a half-typed misspelling finds it ("richi")', got('richi').length === 2, got('richi').join('|'))
check('word order does not matter', got('peter ritchie')[0] === 'Ritchie, Peter' && got('ritchie peter')[0] === 'Ritchie, Peter')
check('a misspelt surname with the right first name picks the right person', got('peter richie').join('|') === 'Ritchie, Peter', got('peter richie').join('|'))
check('an initial stands for a first name', got('p ritchie')[0] === 'Ritchie, Peter')
check('punctuation and case are ignored', got('RITCHIE,  peter')[0] === 'Ritchie, Peter')
check('a name that is not there offers nothing', got('zzzzz').length === 0)
check('two unrelated surnames are not confused', !got('hind').includes('Smith, John') && got('hind')[0] === 'Hind, Darren')
check('an exact find is not labelled a guess', suggest(names, 'ritchie').closest === false)
check('a typo is labelled as the closest matches', suggest(names, 'richie').closest === true)
check('it caps the list and says how many there are', suggest(names, 's', { limit: 1 }).shown.length === 1 && suggest(names, 's', { limit: 1 }).total >= 2)
check('minChars keeps one letter from offering the whole club', suggest(names, 'r', { minChars: 2 }).shown.length === 0)
check('norm strips accents', norm('Müller, José') === 'muller jose')
console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)

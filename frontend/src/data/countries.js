// ICC Full Members + Associate/Affiliate nations that play cricket internationally.
// Used for the datalist on overseas player country fields.

export const CRICKET_COUNTRIES = [
  // Full Members
  'Afghanistan', 'Australia', 'Bangladesh', 'England', 'India',
  'Ireland', 'New Zealand', 'Pakistan', 'South Africa', 'Sri Lanka',
  'West Indies', 'Zimbabwe',
  // Associates & Affiliates
  'Bahrain', 'Belgium', 'Bermuda', 'Bhutan', 'Botswana',
  'Canada', 'Cayman Islands', 'Cook Islands', 'Costa Rica', 'Cyprus',
  'Denmark', 'Estonia', 'Fiji', 'Finland', 'France',
  'Germany', 'Ghana', 'Gibraltar', 'Greece', 'Guernsey',
  'Hong Kong', 'Hungary', 'Indonesia', 'Israel', 'Italy',
  'Japan', 'Jersey', 'Kenya', 'Kuwait', 'Lesotho',
  'Luxembourg', 'Malaysia', 'Maldives', 'Malta', 'Mexico',
  'Mozambique', 'Myanmar', 'Namibia', 'Nepal', 'Netherlands',
  'Nigeria', 'Norway', 'Oman', 'Panama', 'Papua New Guinea',
  'Peru', 'Philippines', 'Portugal', 'Qatar', 'Romania',
  'Rwanda', 'Samoa', 'Saudi Arabia', 'Scotland', 'Sierra Leone',
  'Singapore', 'Spain', 'Sweden', 'Switzerland', 'Tanzania',
  'Thailand', 'Turkey', 'Uganda', 'United Arab Emirates',
  'United States of America', 'Vanuatu', 'Wales', 'Zambia',
]

// ISO 3166-1 alpha-2 codes used to build flagcdn.com image URLs.
// England/Scotland/Wales → 'gb' (subdivision flags not supported on Windows).
// West Indies has no single country code — omitted so no image is shown.
const ISO_CODES = {
  'Afghanistan':              'af',
  'Australia':                'au',
  'Bangladesh':               'bd',
  'England':                  'gb',
  'India':                    'in',
  'Ireland':                  'ie',
  'New Zealand':              'nz',
  'Pakistan':                 'pk',
  'South Africa':             'za',
  'Sri Lanka':                'lk',
  'Zimbabwe':                 'zw',
  'Bahrain':                  'bh',
  'Belgium':                  'be',
  'Bermuda':                  'bm',
  'Botswana':                 'bw',
  'Canada':                   'ca',
  'Cayman Islands':           'ky',
  'Denmark':                  'dk',
  'Fiji':                     'fj',
  'Finland':                  'fi',
  'France':                   'fr',
  'Germany':                  'de',
  'Ghana':                    'gh',
  'Gibraltar':                'gi',
  'Greece':                   'gr',
  'Guernsey':                 'gg',
  'Hong Kong':                'hk',
  'Indonesia':                'id',
  'Israel':                   'il',
  'Italy':                    'it',
  'Japan':                    'jp',
  'Jersey':                   'je',
  'Kenya':                    'ke',
  'Kuwait':                   'kw',
  'Malaysia':                 'my',
  'Maldives':                 'mv',
  'Malta':                    'mt',
  'Mexico':                   'mx',
  'Mozambique':               'mz',
  'Myanmar':                  'mm',
  'Namibia':                  'na',
  'Nepal':                    'np',
  'Netherlands':              'nl',
  'Nigeria':                  'ng',
  'Norway':                   'no',
  'Oman':                     'om',
  'Panama':                   'pa',
  'Papua New Guinea':         'pg',
  'Philippines':              'ph',
  'Portugal':                 'pt',
  'Qatar':                    'qa',
  'Romania':                  'ro',
  'Rwanda':                   'rw',
  'Samoa':                    'ws',
  'Saudi Arabia':             'sa',
  'Scotland':                 'gb',
  'Singapore':                'sg',
  'Spain':                    'es',
  'Sweden':                   'se',
  'Switzerland':              'ch',
  'Tanzania':                 'tz',
  'Thailand':                 'th',
  'Turkey':                   'tr',
  'Uganda':                   'ug',
  'United Arab Emirates':     'ae',
  'United States of America': 'us',
  'Vanuatu':                  'vu',
  'Wales':                    'gb',
  'Zambia':                   'zm',
}

/**
 * Returns a flagcdn.com PNG URL for the given country name, or null if unknown.
 * Render with: <img src={countryFlagUrl(name)} style={{width:20,height:'auto'}} />
 */
export function countryFlagUrl(name) {
  const code = ISO_CODES[name]
  if (!code) return null
  return `https://flagcdn.com/w20/${code}.png`
}

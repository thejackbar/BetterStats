// Clubs shown in the "Trusted by clubs at" logo strip (Landing + Trial pages).
// Real clubs already live on BetterCricket, each pointed at the same uploaded
// logo their own public club page shows (`/api/images/organisations/{id}/logo`)
// rather than a static duplicate — one source of truth for a club's crest.
export const TRUST_CLUBS = [
  { slug: 'applecross', name: 'Applecross Cricket Club', logo: '/marketing/applecross-cc.webp' },
  { slug: 'kalamunda-cricket-club', name: 'Kalamunda Cricket Club', logo: '/marketing/kalamunda-cc.webp' },
  { slug: 'gosnells-cricket-club', name: 'Gosnells Cricket Club', logo: '/marketing/gosnells-cc.webp' },
  { slug: 'leeming-spartan-cricket-club', name: 'Leeming Spartan Cricket Club', logo: '/marketing/leeming-spartan-cc.webp' },
  { slug: 'scarborough-cricket-club', name: 'Scarborough Cricket Club', logo: '/api/images/organisations/6c2fad8f-8ad8-eb11-a7ad-2818780da0cc/logo' },
  { slug: 'yarraville-cricket-club', name: 'Yarraville Cricket Club', logo: '/api/images/organisations/a1e5d8a7-86d8-eb11-a7ad-2818780da0cc/logo' },
  { slug: 'high-wycombe', name: 'High Wycombe Cricket Club', logo: '/api/images/organisations/254939ca-87d8-eb11-a7ad-2818780da0cc/logo' },
  { slug: 'hilton-bicton', name: 'Hilton Bicton Cricket Club', logo: '/api/images/organisations/a82fad8f-8ad8-eb11-a7ad-2818780da0cc/logo' },
]

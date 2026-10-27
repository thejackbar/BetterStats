// The small line icons of the Player Cards page. One stroke, 24 box, currentColor.
const PATHS = {
  home: 'M3 11.5 12 4l9 7.5M5.5 10v9.5h13V10',
  book: 'M5 4.5h10.5A2.5 2.5 0 0 1 18 7v13H7.5A2.5 2.5 0 0 1 5 17.5v-13ZM5 17.5A2.5 2.5 0 0 1 7.5 15H18',
  club: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 0c2.5 2.4 3.8 5.4 3.8 9s-1.3 6.6-3.8 9m0-18C9.5 5.4 8.2 8.4 8.2 12s1.3 6.6 3.8 9M3.5 9.5h17M3.5 14.5h17',
  packs: 'M8 3.5h8l1.5 3v14h-11v-14L8 3.5ZM6.5 6.5h11M10 12h4',
  swaps: 'M4 8h13m0 0-3.5-3.5M17 8l-3.5 3.5M20 16H7m0 0 3.5-3.5M7 16l3.5 3.5',
  help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM9.6 9.4a2.4 2.4 0 1 1 3.4 2.2c-.7.4-1 .9-1 1.6M12 16.8v.2',
  back: 'M10 6l-6 6 6 6M4 12h16',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  heart: 'M12 20s-7.5-4.6-7.5-10A4.2 4.2 0 0 1 12 7.6 4.2 4.2 0 0 1 19.5 10C19.5 15.4 12 20 12 20Z',
  star: 'M12 3.5l2.5 5.2 5.7.8-4.1 4 1 5.7-5.1-2.7-5.1 2.7 1-5.7-4.1-4 5.7-.8L12 3.5Z',
  trophy: 'M8 4h8v5a4 4 0 0 1-8 0V4ZM8 6H5v1.5A3 3 0 0 0 8 10.5M16 6h3v1.5A3 3 0 0 1 16 10.5M12 13v4M8.5 20h7M10 17h4',
  spares: 'M7 7h10v13H7V7ZM9.5 4h10v13',
  link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
  chevron: 'M9 6l6 6-6 6',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  bolt: 'M13 3 5 13.5h6L10 21l8-10.5h-6L13 3Z',
}

export default function Icon({ name, size = 20, className = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={className} style={{ flex: 'none' }}>
      <path d={PATHS[name] || PATHS.star} />
    </svg>
  )
}
